"""Decision Support Tools — The "4-2-1-1" stock selection pipeline.

Tool 1: filter_market_universe — Volume, 200-EMA, relative strength vs Nifty
Tool 2: analyze_technicals     — 20-EMA, RSI entry triggers
Tool 3: check_fundamentals     — Quarterly profit growth from Screener.in
Tool 4: check_sector_health    — Sector index daily performance check (now via sector_agent)

Data source: Kite Connect API only (no yfinance).
Indicators: Manual EMA/RSI calculations (no pandas_ta).
"""

import json
import time
import threading
from datetime import datetime, timedelta
from typing import Any, Callable, Optional

import pandas as pd
from concurrent.futures import ThreadPoolExecutor, as_completed

from agents.decision_support.strategy_config import (
    DEFAULT_RSI_PERIOD,
    DEFAULT_RSI_BUY_LIMIT,
    DEFAULT_EMA_PERIOD,
    DEFAULT_MIN_TURNOVER,
)
from agents.shared.data_infra import (
    PipelineSession,
    clear_session_cache,
    resolve_instrument_tokens,
    fetch_historical,
    fetch_nifty,
    load_universe,
    load_sector_indices,
    get_sector_index_tokens,
    _session_cache as _global_session_cache,
    _sector_index_cache as _global_sector_cache,
)
from agents.shared.quant_agent import compute_indicators, compute_relative_strength
from agents.shared.fundamentals_agent import enrich_with_fundamentals
from agents.shared.sector_agent import enrich_with_sector
from agents.shared.news_agent import fetch_news_batch
from broker import get_broker
from config import DATA_DIR
from constants import (
    ADX_PIPELINE_MIN,
    STRICT_ROE_MIN,
    STRICT_DE_MAX,
    SECTOR_5D_TOLERANCE,
    SECTOR_HISTORY_CALENDAR_DAYS,
    MIN_VOLUME_RATIO,
    YOY_QUARTERS_NEEDED,
    NEWS_LOOKBACK_DAYS,
    CLAUDE_CONVICTION_THINKING_BUDGET,
)
from services.technical import calculate_adx, calculate_rsi as _canonical_rsi

# Re-export clear_session_cache so stream.py can import from here (backward compat)
__all__ = [
    "clear_session_cache",
    "filter_market_universe",
    "analyze_technicals",
    "check_fundamentals",
    "check_sector_health",
    "compute_composite_scores",
    "ai_rank_stocks",
    "rank_final_shortlist",
]



def _get_kite(access_token: str):
    broker = get_broker(access_token)
    return broker.raw_kite


# ---------------------------------------------------------------------------
# Tool 1: Universe Filter
# ---------------------------------------------------------------------------

def filter_market_universe(
    access_token: str,
    log: Callable[[str], None] = print,
    min_turnover: int = DEFAULT_MIN_TURNOVER,
    ema_period: int = DEFAULT_EMA_PERIOD,
    universe: str = "nifty500",
    session: Optional[PipelineSession] = None,
) -> list[dict]:
    """Filter stock universe: turnover, volume trend, 200-EMA, relative strength vs Nifty + sector.

    Returns list of stock dicts with keys:
        symbol, instrument_token, sector, sector_index, current_price,
        avg_volume_20d, avg_turnover_20d, ema_200, volume_ratio,
        stock_3m_return, nifty_3m_return, sector_3m_return
    """
    kite = _get_kite(access_token)
    stocks_df = load_universe(universe, session=session)
    total = len(stocks_df)
    universe_label = universe.replace("_", " ").title()
    log(f"Loaded {universe_label} list: {total} stocks")

    # --- Step 1: Fetch Nifty 50 data for relative strength ----------------
    nifty_df = fetch_nifty(kite, session=session)
    nifty_3m_return = 0.0
    if nifty_df is not None and len(nifty_df) >= 63:
        nifty_3m_return = (
            (nifty_df["Close"].iloc[-1] / nifty_df["Close"].iloc[-63]) - 1
        ) * 100
    log(f"Nifty 50 3-month return: {nifty_3m_return:.2f}%")

    # --- Step 2: Resolve real instrument tokens from Kite API -------------
    token_map = resolve_instrument_tokens(kite, log, session=session)

    # --- Step 3: Pre-fetch sector index data for sector-relative strength --
    # Use session-scoped cache when available, else fall back to global
    sector_cache = session.sector_index_cache if session is not None else _global_sector_cache
    sector_indices_needed: set[str] = set()
    for _, row in stocks_df.iterrows():
        si = row.get("sector_index")
        if si and pd.notna(si):
            sector_indices_needed.add(si)

    sector_token_map = get_sector_index_tokens(token_map)
    for idx_symbol in sector_indices_needed:
        token = sector_token_map.get(idx_symbol)
        if token and idx_symbol not in sector_cache:
            df = fetch_historical(kite, token, idx_symbol, days=400, session=session)
            if df is not None:
                sector_cache[idx_symbol] = df
            time.sleep(0.35)
    log(f"Pre-fetched {len(sector_cache)} sector index histories for relative strength")

    # --- Step 4: Build stock list with resolved tokens --------------------
    all_stocks = []
    skipped = 0
    for _, row in stocks_df.iterrows():
        symbol = row["symbol"]
        real_token = token_map.get(symbol)
        if real_token is None:
            skipped += 1
            continue
        all_stocks.append({
            "symbol": symbol,
            "instrument_token": real_token,
            "sector": row["sector"],
            "sector_index": row["sector_index"],
        })
    if skipped:
        log(f"Skipped {skipped} stocks (not found in NSE instruments)")

    rate_lock = threading.Lock()
    request_count = [0]
    counters = {
        "fetch_failed": 0,
        "too_few_candles": 0,
        "turnover_rejected": 0,
        "volume_trend_rejected": 0,
        "ema_nan": 0,
        "ema_rejected": 0,
        "nifty_rs_rejected": 0,
        "sector_rs_rejected": 0,
        "passed": 0,
    }

    def fetch_and_filter(stock: dict) -> Optional[dict]:
        with rate_lock:
            request_count[0] += 1
            time.sleep(0.35)

        df = fetch_historical(kite, stock["instrument_token"], stock["symbol"], days=400, session=session)
        if df is None:
            with rate_lock:
                counters["fetch_failed"] += 1
            return None
        if len(df) < 200:
            with rate_lock:
                counters["too_few_candles"] += 1
            return None

        # --- Turnover filter: 20-day avg (price x volume) ------------------
        avg_volume_20d = df["Volume"].tail(20).mean()
        avg_price_20d = df["Close"].tail(20).mean()
        avg_turnover_20d = avg_volume_20d * avg_price_20d
        if avg_turnover_20d < min_turnover:
            with rate_lock:
                counters["turnover_rejected"] += 1
            return None

        # --- Volume trend filter: 5-day vs 20-day avg volume ---------------
        avg_volume_5d = df["Volume"].tail(5).mean()
        volume_ratio = (avg_volume_5d / avg_volume_20d) if avg_volume_20d > 0 else 1.0
        if volume_ratio < MIN_VOLUME_RATIO:
            with rate_lock:
                counters["volume_trend_rejected"] += 1
            return None

        # --- EMA filter ---------------------------------------------------
        ema_val = df["Close"].ewm(span=ema_period, adjust=False).mean().iloc[-1]
        current_price = df["Close"].iloc[-1]

        if pd.isna(ema_val):
            with rate_lock:
                counters["ema_nan"] += 1
            return None

        if current_price <= ema_val:
            with rate_lock:
                counters["ema_rejected"] += 1
            return None

        # --- 3-month relative strength vs Nifty ---------------------------
        if len(df) >= 63:
            stock_3m_return = ((current_price / df["Close"].iloc[-63]) - 1) * 100
        else:
            stock_3m_return = 0.0

        if stock_3m_return <= nifty_3m_return:
            with rate_lock:
                counters["nifty_rs_rejected"] += 1
            return None

        # --- 3-month relative strength vs sector index --------------------
        sector_3m_return = None
        sector_idx = stock.get("sector_index")
        if sector_idx and sector_idx in sector_cache:
            sector_df = sector_cache[sector_idx]
            if len(sector_df) >= 63:
                sector_3m_return = (
                    (sector_df["Close"].iloc[-1] / sector_df["Close"].iloc[-63]) - 1
                ) * 100
                if stock_3m_return <= sector_3m_return:
                    with rate_lock:
                        counters["sector_rs_rejected"] += 1
                    return None

        with rate_lock:
            counters["passed"] += 1

        stock["current_price"] = round(current_price, 2)
        stock["avg_volume_20d"] = round(avg_volume_20d, 0)
        stock["avg_turnover_20d"] = round(avg_turnover_20d, 0)
        stock["volume_ratio"] = round(volume_ratio, 2)
        stock["ema_200"] = round(ema_val, 2)
        stock["stock_3m_return"] = round(stock_3m_return, 2)
        stock["nifty_3m_return"] = round(nifty_3m_return, 2)
        if sector_3m_return is not None:
            stock["sector_3m_return"] = round(sector_3m_return, 2)
        return stock

    passed = []
    log(f"Fetching historical data for {len(all_stocks)} stocks (this may take a few minutes)...")
    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = {
            executor.submit(fetch_and_filter, s): s["symbol"]
            for s in all_stocks
        }
        done_count = 0
        for future in as_completed(futures):
            done_count += 1
            if done_count % 50 == 0:
                log(f"Processed {done_count} / {len(all_stocks)} stocks...")
            result = future.result()
            if result is not None:
                passed.append(result)

    log(f"--- Filter breakdown ---")
    log(f"  Total stocks:         {len(all_stocks)}")
    log(f"  Fetch failed:         {counters['fetch_failed']}")
    log(f"  Too few candles:      {counters['too_few_candles']}")
    log(f"  Turnover too low:     {counters['turnover_rejected']}")
    log(f"  Volume trend weak:    {counters['volume_trend_rejected']}")
    log(f"  EMA NaN:              {counters['ema_nan']}")
    log(f"  Price <= 200-EMA:     {counters['ema_rejected']}")
    log(f"  Nifty RS fail:        {counters['nifty_rs_rejected']}")
    log(f"  Sector RS fail:       {counters['sector_rs_rejected']}")
    log(f"  PASSED:               {counters['passed']}")

    log(f"Universe filter complete: {len(passed)} / {len(all_stocks)} stocks passed")
    return passed


# ---------------------------------------------------------------------------
# Tool 2: Technical Setup
# ---------------------------------------------------------------------------

def analyze_technicals(
    stocks: list[dict],
    log: Callable[[str], None] = print,
    rsi_buy_limit: int = DEFAULT_RSI_BUY_LIMIT,
    session: Optional[PipelineSession] = None,
) -> list[dict]:
    """Filter by EMA, ADX trend strength, and RSI entry triggers.

    Pullback trigger: Price > 200-EMA (relaxed, can be below 20-EMA) + RSI < rsi_buy_limit
    Momentum trigger: Price > 20-EMA + RSI crossed above 50 in last 5 days
    Both require: ADX >= ADX_PIPELINE_MIN (trend confirmation)

    Uses cached historical data from Tool 1 (no new API calls).
    """
    # Use session cache if available, else fall back to module-level global
    cache = session.session_cache if session is not None else _global_session_cache

    passed = []
    counters = {"no_data": 0, "adx_weak": 0, "no_trigger": 0, "passed": 0}

    for stock in stocks:
        token = stock["instrument_token"]
        df = cache.get(token)
        if df is None or len(df) < 50:
            counters["no_data"] += 1
            continue

        current_price = df["Close"].iloc[-1]
        ema_20 = df["Close"].ewm(span=20, adjust=False).mean().iloc[-1]
        ema_200 = stock.get("ema_200") or df["Close"].ewm(span=200, adjust=False).mean().iloc[-1]

        # ADX trend strength gate
        adx_val = calculate_adx(df)
        if adx_val is None or pd.isna(adx_val) or adx_val < ADX_PIPELINE_MIN:
            counters["adx_weak"] += 1
            continue

        rsi_series = _canonical_rsi(df["Close"], 14)
        if rsi_series.empty or rsi_series.isna().all():
            counters["no_data"] += 1
            continue
        current_rsi = rsi_series.iloc[-1]

        # Determine trigger type
        pullback = current_rsi < rsi_buy_limit
        momentum = False
        if len(rsi_series) >= 6:
            for i in range(-5, 0):
                if rsi_series.iloc[i - 1] < 50 <= rsi_series.iloc[i]:
                    momentum = True
                    break

        if pullback:
            # Pullback: price must be above 200-EMA (can be below 20-EMA)
            if current_price <= ema_200:
                counters["no_trigger"] += 1
                continue
        elif momentum:
            # Momentum: price must be above 20-EMA
            if current_price <= ema_20:
                counters["no_trigger"] += 1
                continue
        else:
            counters["no_trigger"] += 1
            continue

        counters["passed"] += 1
        stock["ema_20"] = round(ema_20, 2)
        stock["rsi"] = round(current_rsi, 2)
        stock["adx"] = round(adx_val, 2)
        stock["rsi_trigger"] = "pullback" if pullback else "momentum"
        passed.append(stock)

    log(f"--- Technical filter breakdown ---")
    log(f"  No data/too few bars: {counters['no_data']}")
    log(f"  ADX too weak (<{ADX_PIPELINE_MIN}): {counters['adx_weak']}")
    log(f"  No trigger fired:     {counters['no_trigger']}")
    log(f"  PASSED:               {counters['passed']}")
    log(f"Technical setup filter: {len(passed)} / {len(stocks)} passed")
    return passed


# ---------------------------------------------------------------------------
# Tool 3: Fundamental Check (Screener.in quarterly profits)
# ---------------------------------------------------------------------------

def check_fundamentals(
    stocks: list[dict],
    log: Callable[[str], None] = print,
    fundamental_check: str = "standard",
    session: Optional[PipelineSession] = None,
) -> list[dict]:
    """Filter stocks based on fundamental health via shared fundamentals_agent.

    Args:
        fundamental_check: one of "strict", "standard", "loose", "none".
            - strict:   YoY profit growth + ROE > 15 + D/E < 1.0 (Gear 1)
            - standard: YoY profit growth (fallback to QoQ if < 5 quarters)
            - loose:    latest quarter net profit > 0 (not loss-making)
            - none:     skip check entirely, pass all stocks through
    """
    if fundamental_check == "none":
        log("Fundamental filter: skipped (gear set to 'none')")
        return list(stocks)

    mode_map = {
        "strict": "filter_strict",
        "standard": "filter_standard",
        "loose": "filter_loose",
        "none": "filter_none",
    }
    mode = mode_map.get(fundamental_check, "filter_standard")
    return enrich_with_fundamentals(stocks, log=log, mode=mode, session=session)


# ---------------------------------------------------------------------------
# Tool 4: Sector Health Check
# ---------------------------------------------------------------------------

def check_sector_health(
    access_token: str,
    stocks: list[dict],
    log: Callable[[str], None] = print,
    session: Optional[PipelineSession] = None,
) -> list[dict]:
    """Keep stocks whose sector index has non-negative 5-day performance (with tolerance).

    Delegates to shared sector_agent with mode="filter".
    """
    if not stocks:
        return []
    kite = _get_kite(access_token)
    return enrich_with_sector(
        stocks, kite, log=log,
        mode="filter",
        tolerance=SECTOR_5D_TOLERANCE,
        include_3m=False,
        session=session,
    )


# ---------------------------------------------------------------------------
# Composite Scoring
# ---------------------------------------------------------------------------

def compute_composite_scores(stocks: list[dict], log: Callable[[str], None] = print, session: Optional[PipelineSession] = None) -> list[dict]:
    """Assign 0-100 composite score to each stock and sort descending.

    Scoring breakdown (0-25 each dimension):
      Technical:          RSI entry quality + ADX strength + EMA distance
      Fundamental:        Profit growth signals + ROE quality
      Relative Strength:  Nifty outperformance + sector outperformance
      Volume Health:      Volume ratio + turnover magnitude
    """
    for stock in stocks:
        # --- Technical (0-25) ---
        tech_score = 0
        rsi = stock.get("rsi", 50)
        if stock.get("rsi_trigger") == "pullback":
            tech_score += max(0, min(10, int((50 - rsi) / 3)))
        else:
            tech_score += 5  # momentum gets flat 5

        adx = stock.get("adx", 0)
        tech_score += min(10, int(adx / 4))

        price = stock.get("current_price", 0)
        ema200 = stock.get("ema_200", price)
        if ema200 > 0:
            ema_dist_pct = ((price - ema200) / ema200) * 100
            tech_score += min(5, int(ema_dist_pct / 5))

        # --- Fundamental (0-25) ---
        fund_score = 0
        if stock.get("quarterly_profit_growth"):
            fund_score += 8
        if stock.get("profit_yoy_growing"):
            fund_score += 7
        elif stock.get("quarterly_profit_positive"):
            fund_score += 4

        roe = stock.get("roe")
        if roe is not None:
            if roe > 20:
                fund_score += 10
            elif roe > 15:
                fund_score += 7
            elif roe > 10:
                fund_score += 4
        else:
            fund_score += 5  # neutral when unavailable

        # --- Relative Strength (0-25) ---
        rs_score = 0
        stock_ret = stock.get("stock_3m_return", 0)
        nifty_ret = stock.get("nifty_3m_return", 0)
        outperformance = stock_ret - nifty_ret
        rs_score += min(15, max(0, int(outperformance / 2)))

        sector_ret = stock.get("sector_3m_return")
        if sector_ret is not None:
            sector_op = stock_ret - sector_ret
            rs_score += min(10, max(0, int(sector_op / 2)))
        else:
            rs_score += 5

        # --- Volume Health (0-25) ---
        vol_score = 0
        vol_ratio = stock.get("volume_ratio", 1.0)
        vol_score += min(15, int(vol_ratio * 10))
        turnover = stock.get("avg_turnover_20d", 0)
        if turnover > 500_000_000:
            vol_score += 10
        elif turnover > 100_000_000:
            vol_score += 7
        elif turnover > 50_000_000:
            vol_score += 4
        elif turnover > 20_000_000:
            vol_score += 2

        composite = min(100, min(25, tech_score) + min(25, fund_score) + min(25, rs_score) + min(25, vol_score))
        stock["composite_score"] = composite
        stock["score_breakdown"] = {
            "technical": min(25, tech_score),
            "fundamental": min(25, fund_score),
            "relative_strength": min(25, rs_score),
            "volume_health": min(25, vol_score),
        }

    stocks.sort(key=lambda s: s.get("composite_score", 0), reverse=True)
    if stocks:
        log(
            f"Composite scores computed. Top: {stocks[0]['symbol']}={stocks[0]['composite_score']}, "
            f"Bottom: {stocks[-1]['symbol']}={stocks[-1]['composite_score']}"
        )
    return stocks


# ---------------------------------------------------------------------------
# AI-Powered Stock Ranking (Agent 5 — AI Conviction Engine)
# ---------------------------------------------------------------------------

def ai_rank_stocks(
    stocks: list[dict],
    market_regime: dict,
    log: Callable[[str], None] = print,
    llm_provider: Optional[str] = None,
    user_id: Optional[int] = None,
    session: Optional[PipelineSession] = None,
) -> list[dict]:
    """AI-powered stock ranking with news sentiment analysis.

    Always uses Claude with extended thinking (provider="claude").
    For each stock:
    1. Fetches recent news headlines
    2. Sends all data (technical, fundamental, news, market context) to LLM
    3. Gets conviction score (1-10), reason, and news sentiment
    """
    from agents.config import get_llm

    llm = get_llm(
        temperature=0.1,
        provider="claude",
        extended_thinking=True,
        thinking_budget=CLAUDE_CONVICTION_THINKING_BUDGET,
        user_id=user_id,
        pipeline="buy",
    )

    # Fetch news for all stocks in parallel
    symbols = [s["symbol"] for s in stocks]
    news_map = fetch_news_batch(symbols, log=log)
    log("News fetched. Building AI ranking prompt...")

    # Build prompt with all context
    stock_data_lines = []
    for s in stocks:
        headlines = news_map.get(s["symbol"], [])
        headline_text = "; ".join([h["title"] for h in headlines[:5]]) if headlines else "No recent news found"

        stock_data_lines.append(
            f"- {s['symbol']}: Price={s.get('current_price')}, RSI={s.get('rsi')}, "
            f"ADX={s.get('adx')}, Trigger={s.get('rsi_trigger')}, "
            f"Sector={s.get('sector')}, 3M Return={s.get('stock_3m_return')}%, "
            f"Nifty 3M={s.get('nifty_3m_return')}%, "
            f"Sector 3M={s.get('sector_3m_return', 'N/A')}%, "
            f"Composite={s.get('composite_score')}, "
            f"Vol Ratio={s.get('volume_ratio')}, "
            f"ROE={s.get('roe', 'N/A')}, D/E={s.get('debt_to_equity', 'N/A')}, "
            f"Recent News: {headline_text}"
        )

    vix = market_regime.get("vix", "N/A")
    regime = market_regime.get("regime", "unknown")
    vix_high = isinstance(vix, (int, float)) and vix > 20

    vix_note = (
        f"\nCAUTION: VIX={vix} is elevated (>20). Penalize high-beta stocks and downgrade momentum setups. "
        "Favor defensive names and pullback entries over breakouts."
        if vix_high else ""
    )
    prompt = (
        "You are a senior trading analyst evaluating Indian NSE stocks that passed a 4-stage screening pipeline.\n\n"
        f"Market Context:\n"
        f"- India VIX: {vix} (Regime: {regime}){vix_note}\n"
        f"- {len(stocks)} stocks survived from the pipeline\n\n"
        f"Stock Data:\n"
        + "\n".join(stock_data_lines)
        + "\n\nFor EACH stock provide a JSON object with these exact keys:\n"
        "{\n"
        '  "symbol": "<symbol>",\n'
        '  "conviction_score": <integer 1-10, 10=highest conviction>,\n'
        '  "reason": "<one sentence max 25 words explaining the trade opportunity>",\n'
        '  "primary_risk": "<single biggest bear case — the one thing that could make this trade fail>",\n'
        '  "trade_type": "pullback_entry" | "momentum_breakout" | "accumulate_dip",\n'
        '  "news_sentiment": <integer 1-5>,\n'
        '  "news_flag": "warning" | "clear"\n'
        "}\n\n"
        "Consider: technical setup quality, fundamental strength, news, sector momentum, "
        "market regime (VIX), and entry quality.\n\n"
        "Return ONLY a JSON array of these objects, no markdown, no extra text."
    )

    try:
        from agents.output_schemas import ConvictionScore
        from pydantic import ValidationError
        from services.cache_service import llm_cache_key, cache_get, cache_set

        # Check LLM output cache (avoid re-running expensive extended-thinking call)
        _llm_cache_key = llm_cache_key("buy", prompt)
        _cached = cache_get(_llm_cache_key)
        if _cached:
            content = _cached.decode("utf-8")
            log("AI ranking: using cached LLM response")
        else:
            response = llm.invoke(prompt)
            content = response.content.strip()
            cache_set(_llm_cache_key, content.encode("utf-8"))
        if "```" in content:
            content = content.split("```")[1]
            if content.startswith("json"):
                content = content[4:]
            content = content.strip()
        raw_rankings = json.loads(content)

        ranking_map: dict[str, ConvictionScore] = {}
        for item in raw_rankings:
            try:
                validated = ConvictionScore.model_validate(item)
                ranking_map[validated.symbol] = validated
            except ValidationError as ve:
                log(f"  AI ranking: validation warning for {item.get('symbol', '?')}: {ve.error_count()} error(s) — using defaults")

        for s in stocks:
            rank_data = ranking_map.get(s["symbol"])
            if rank_data:
                s["ai_conviction"] = rank_data.conviction_score
                s["why_selected"] = rank_data.reason or f"Passed all filters with RSI {s.get('rsi', 'N/A')}"
                s["news_sentiment"] = rank_data.news_sentiment
                s["news_flag"] = rank_data.news_flag
                s["primary_risk"] = rank_data.primary_risk
                s["trade_type"] = rank_data.trade_type
            else:
                s["ai_conviction"] = 5
                s["why_selected"] = f"Passed all filters with RSI {s.get('rsi', 'N/A')}"
                s["news_sentiment"] = 3
                s["news_flag"] = "clear"
            s["news_headlines"] = [h["title"] for h in news_map.get(s["symbol"], [])[:3]]

        log(f"AI ranking complete for {len(stocks)} stocks")

    except Exception as e:
        log(f"AI ranking failed: {e}. Using fallback reasons.")
        for s in stocks:
            s["ai_conviction"] = 5
            s["why_selected"] = (
                f"RSI {s.get('rsi', 'N/A')} {s.get('rsi_trigger', '')} setup, "
                f"composite score {s.get('composite_score', 'N/A')}"
            )
            s["news_sentiment"] = 3
            s["news_flag"] = "clear"
            s["news_headlines"] = [h["title"] for h in news_map.get(s["symbol"], [])[:3]]

    # Sort by AI conviction (primary), then composite score (secondary)
    stocks.sort(key=lambda s: (s.get("ai_conviction", 0), s.get("composite_score", 0)), reverse=True)
    return stocks


# ---------------------------------------------------------------------------
# Portfolio Ranker — Agent 6
# ---------------------------------------------------------------------------

def rank_final_shortlist(
    stocks: list[dict],
    log: Callable[[str], None] = print,
    llm_provider: Optional[str] = None,
    user_id: Optional[int] = None,
    session: Optional[PipelineSession] = None,
) -> list[dict]:
    """Agent 6 — Portfolio Ranker.

    Takes the final shortlist (after all 5 pipeline stages) and produces a
    transparent multi-factor final ranking. Uses OpenAI for rank explanations.

    Weights:
      35% AI conviction  (normalized 1-10 → 0-100)
      25% composite score (already 0-100)
      15% relative strength vs Nifty (min-max over batch)
      15% fundamental quality (ROE + D/E + profit growth → 0-100)
      10% sector momentum (min-max over batch)

    Adds fields: final_rank, final_rank_score, rank_reason, rank_factors.
    """
    import re as _re

    if not stocks:
        return stocks

    def _minmax(vals: list[float]) -> list[float]:
        lo, hi = min(vals), max(vals)
        if hi == lo:
            return [50.0] * len(vals)
        return [(v - lo) / (hi - lo) * 100 for v in vals]

    def _fundamental_score(s: dict) -> float:
        score = 0
        roe = s.get("roe") or 0
        de = s.get("debt_to_equity") or 99
        if roe > 20:
            score += 40
        elif roe > 15:
            score += 30
        elif roe > 10:
            score += 20
        elif roe > 5:
            score += 10
        if de < 0.5:
            score += 30
        elif de < 1.0:
            score += 25
        elif de < 2.0:
            score += 15
        elif de < 3.0:
            score += 5
        if s.get("profit_yoy_growing"):
            score += 30
        elif s.get("profit_qoq_growing"):
            score += 20
        return min(100.0, float(score))

    # Normalize each factor across the batch
    conviction_raw = [((s.get("ai_conviction") or 5) - 1) / 9 * 100 for s in stocks]
    composite_raw  = [float(s.get("composite_score") or 50) for s in stocks]
    rs_raw = [
        (s.get("stock_3m_return") or 0) - (s.get("nifty_3m_return") or 0)
        for s in stocks
    ]
    fund_raw    = [_fundamental_score(s) for s in stocks]
    sector_raw  = [s.get("sector_5d_change") or 0 for s in stocks]

    conv_norm   = _minmax(conviction_raw)
    comp_norm   = _minmax(composite_raw)
    rs_norm     = _minmax(rs_raw)
    fund_norm   = _minmax(fund_raw)
    sector_norm = _minmax(sector_raw)

    for i, s in enumerate(stocks):
        s["rank_factors"] = {
            "ai_conviction_norm":     round(conv_norm[i], 1),
            "composite_score_norm":   round(comp_norm[i], 1),
            "relative_strength_norm": round(rs_norm[i], 1),
            "fundamental_norm":       round(fund_norm[i], 1),
            "sector_momentum_norm":   round(sector_norm[i], 1),
        }
        s["final_rank_score"] = round(
            0.35 * conv_norm[i]
            + 0.25 * comp_norm[i]
            + 0.15 * rs_norm[i]
            + 0.15 * fund_norm[i]
            + 0.10 * sector_norm[i],
            1,
        )

    stocks.sort(key=lambda x: x["final_rank_score"], reverse=True)
    for rank, s in enumerate(stocks, 1):
        s["final_rank"] = rank
        log(f"#{rank} {s['symbol']} — rank score {s['final_rank_score']:.1f}/100")

    # LLM rank explanations — always use OpenAI for lightweight ranking
    try:
        from agents.config import get_llm
        llm = get_llm(temperature=0.2, provider="openai", user_id=user_id, pipeline="rank")

        summary_lines = []
        for s in stocks:
            rs_diff = (s.get("stock_3m_return") or 0) - (s.get("nifty_3m_return") or 0)
            summary_lines.append(
                f"Rank #{s['final_rank']} {s['symbol']}: "
                f"AI conviction {s.get('ai_conviction', '-')}/10, "
                f"composite {s.get('composite_score', '-')}/100, "
                f"3M RS vs Nifty {rs_diff:+.1f}%, "
                f"ROE {s.get('roe') or 'n/a'}, D/E {s.get('debt_to_equity') or 'n/a'}, "
                f"sector {s.get('sector', 'N/A')}, "
                f"sector 5d {s.get('sector_5d_change', 0):+.2f}%, "
                f"rank score {s['final_rank_score']}"
            )

        # Identify sector distribution for concentration warnings
        sectors = [s.get("sector", "Unknown") for s in stocks]
        from collections import Counter
        sector_counts = Counter(sectors)

        prompt = (
            "You are a portfolio analyst. These stocks are ranked by a multi-factor formula "
            "(AI conviction 35%, composite 25%, relative strength 15%, fundamentals 15%, sector momentum 10%).\n\n"
            f"Portfolio sector distribution: {dict(sector_counts)}\n\n"
            "For each stock provide a JSON object with:\n"
            "{\n"
            '  "symbol": "<symbol>",\n'
            '  "rank_reason": "<1 sentence max 25 words: why this rank, citing 2-3 strongest signals>",\n'
            '  "portfolio_note": "diversified" | "sector_concentration_risk" | "correlated_with_rank_1"\n'
            "}\n\n"
            "portfolio_note rules:\n"
            "- sector_concentration_risk: if this stock's sector appears 3+ times in the portfolio\n"
            "- correlated_with_rank_1: if this stock's sector matches rank #1's sector AND it's not rank #1\n"
            "- diversified: otherwise\n\n"
            + "\n".join(summary_lines)
            + "\n\nReturn ONLY a JSON array of these objects, no markdown, no extra text."
        )

        response = llm.invoke(prompt)
        raw = response.content.strip() if hasattr(response, "content") else str(response)
        if "```" in raw:
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
            raw = raw.strip()
        m = _re.search(r"\[.*\]", raw, _re.DOTALL)
        if m:
            from agents.output_schemas import PortfolioRank
            from pydantic import ValidationError as _VE
            raw_reasons = json.loads(m.group())
            reason_map: dict[str, PortfolioRank] = {}
            for item in raw_reasons:
                try:
                    validated = PortfolioRank.model_validate(item)
                    reason_map[validated.symbol] = validated
                except _VE:
                    pass  # use formula fallback for this symbol
            for s in stocks:
                entry = reason_map.get(s["symbol"])
                if entry:
                    s["rank_reason"] = entry.rank_reason
                    s["portfolio_note"] = entry.portfolio_note
                else:
                    s.setdefault("rank_reason", "")
                    s.setdefault("portfolio_note", "diversified")
            log(f"Portfolio Ranker: LLM explanations generated for {len(stocks)} stocks")
    except Exception as e:
        log(f"Portfolio Ranker LLM failed ({e}), using formula fallback.")
        for s in stocks:
            s["rank_reason"] = (
                f"Ranked #{s['final_rank']} with weighted score {s['final_rank_score']:.0f}/100 "
                f"(AI conviction {s.get('ai_conviction', 5)}/10, "
                f"composite {s.get('composite_score', 50)}/100)."
            )

    return stocks
