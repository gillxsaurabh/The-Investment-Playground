"""Sell Analysis Tools — Portfolio audit pipeline.

Analyzes the user's current portfolio holdings for sell urgency.
Unlike the buy pipeline (which scans universe CSVs and filters down),
this pipeline starts with actual holdings and scores ALL of them —
no holdings are eliminated, every one receives a sell urgency score.

Stages:
  1. fetch_portfolio_holdings         — fetch live holdings + resolve tokens + sector lookup
  2. enrich_with_technicals           — RSI, ADX, EMA-20/50/200, ATR, 3M RS (shared module)
  3. enrich_with_fundamentals         — quarterly profit trend, ROE, D/E (shared module)
  4. enrich_with_sector               — 5-day sector index performance (shared module)
  5. compute_sell_scores + ai_rank_sell_candidates — urgency score + LLM reasoning
"""

import json
from datetime import datetime
from typing import Callable, Optional

from agents.shared.data_infra import (
    PipelineSession,
    clear_session_cache,
    resolve_instrument_tokens,
    build_symbol_sector_map,
)
from agents.shared.news_agent import fetch_news_batch
from broker import get_broker
from constants import (
    NEWS_LOOKBACK_DAYS,
    SELL_RSI_OVERBOUGHT,
    SELL_RSI_MOMENTUM_FAILED,
    SELL_ADX_WEAK,
    SELL_RS_NIFTY_GAP,
    SELL_RS_SECTOR_GAP,
    SELL_PROFIT_DECLINE_QUARTERS,
    SELL_ROE_WEAK,
    SELL_ROE_MODERATE,
    SELL_DE_HIGH,
    SELL_PNL_LOSS_THRESHOLD,
    SELL_PNL_DEEP_LOSS_THRESHOLD,
    SELL_URGENCY_STRONG,
    SELL_URGENCY_SELL,
    SELL_URGENCY_WATCH,
    SELL_HISTORICAL_DAYS,
    SELL_MOMENTUM_LOOKBACK,
    SELL_VOLUME_DRY_RATIO,
    CLAUDE_CONVICTION_THINKING_BUDGET,
)

# Re-export shared enrichment functions under old names for backward compat
from agents.shared.quant_agent import enrich_with_technicals
from agents.shared.fundamentals_agent import enrich_with_fundamentals
from agents.shared.sector_agent import enrich_with_sector

# Also re-export clear_session_cache so sell_stream.py can keep its import path
__all__ = [
    "clear_sell_session_cache",
    "clear_session_cache",
    "fetch_portfolio_holdings",
    "enrich_with_technicals",
    "enrich_holdings_with_technicals",
    "enrich_with_fundamentals",
    "enrich_holdings_with_fundamentals",
    "enrich_with_sector",
    "enrich_holdings_with_sector",
    "compute_sell_scores",
    "ai_rank_sell_candidates",
]


def clear_sell_session_cache():
    """Backward-compat alias — delegates to shared data_infra.clear_session_cache()."""
    clear_session_cache()


# ---------------------------------------------------------------------------
# Backward-compat wrappers (sell_stream.py and audit_pipeline.py use these names)
# ---------------------------------------------------------------------------

def enrich_holdings_with_technicals(
    holdings: list[dict],
    kite,
    log: Callable[[str], None] = print,
    session: Optional[PipelineSession] = None,
) -> list[dict]:
    """Backward-compat wrapper — delegates to shared quant_agent.enrich_with_technicals."""
    return enrich_with_technicals(
        holdings, kite,
        log=log,
        mode="enrich",
        historical_days=SELL_HISTORICAL_DAYS,
        session=session,
    )


def enrich_holdings_with_fundamentals(
    holdings: list[dict],
    log: Callable[[str], None] = print,
    session: Optional[PipelineSession] = None,
) -> list[dict]:
    """Backward-compat wrapper — delegates to shared fundamentals_agent.enrich_with_fundamentals."""
    return enrich_with_fundamentals(holdings, log=log, mode="enrich", session=session)


def enrich_holdings_with_sector(
    holdings: list[dict],
    access_token: str,
    log: Callable[[str], None] = print,
    session: Optional[PipelineSession] = None,
) -> list[dict]:
    """Backward-compat wrapper — delegates to shared sector_agent.enrich_with_sector."""
    broker = get_broker(access_token)
    kite = broker.raw_kite
    return enrich_with_sector(holdings, kite, log=log, mode="enrich", include_3m=True, session=session)


# ---------------------------------------------------------------------------
# Stage 1: Fetch Portfolio Holdings
# ---------------------------------------------------------------------------

def fetch_portfolio_holdings(
    access_token: str,
    log: Callable[[str], None] = print,
    session: Optional[PipelineSession] = None,
) -> list[dict]:
    """Fetch live holdings from broker, resolve instrument tokens, attach sector info.

    Returns list of holding dicts with keys:
        symbol, exchange, quantity, average_price, last_price, pnl, pnl_percentage,
        instrument_token, sector, sector_index
    """
    broker = get_broker(access_token)
    kite = broker.raw_kite

    log("Fetching live portfolio holdings from Kite...")
    raw_holdings = broker.get_holdings()

    if not raw_holdings:
        log("No holdings found in portfolio.")
        return []

    log(f"Found {len(raw_holdings)} holdings. Resolving instrument tokens...")
    token_map = resolve_instrument_tokens(kite, log, session=session)
    sector_map = build_symbol_sector_map(log, session=session)

    holdings = []
    skipped = 0
    for h in raw_holdings:
        symbol = h.get("tradingsymbol") or h.get("symbol", "")
        if not symbol:
            skipped += 1
            continue

        instrument_token = token_map.get(symbol)
        if instrument_token is None:
            log(f"  Skipping {symbol}: not found in NSE instruments")
            skipped += 1
            continue

        sector_info = sector_map.get(symbol, {"sector": "Unknown", "sector_index": None})

        quantity = h.get("quantity", 0)
        average_price = h.get("average_price", 0.0)
        last_price = h.get("last_price", 0.0)
        pnl = h.get("pnl", 0.0)

        if average_price and average_price > 0:
            pnl_percentage = ((last_price - average_price) / average_price) * 100
        else:
            pnl_percentage = 0.0

        holdings.append({
            "symbol": symbol,
            "exchange": h.get("exchange", "NSE"),
            "quantity": quantity,
            "average_price": round(average_price, 2),
            "last_price": round(last_price, 2),
            "pnl": round(pnl, 2),
            "pnl_percentage": round(pnl_percentage, 2),
            "instrument_token": instrument_token,
            "sector": sector_info["sector"],
            "sector_index": sector_info["sector_index"],
        })

    if skipped:
        log(f"Skipped {skipped} holdings (no token or no symbol)")
    log(f"Portfolio Inspector: {len(holdings)} holdings ready for analysis")
    return holdings


# ---------------------------------------------------------------------------
# Stage 5a: Compute Sell Urgency Scores
# ---------------------------------------------------------------------------

def _score_technical_breakdown(holding: dict) -> tuple[int, list[str]]:
    """Score 0-38 based on technical deterioration signals (including volume)."""
    score = 0
    signals = []

    price = holding.get("current_price") or holding.get("last_price")
    rsi = holding.get("rsi")
    adx = holding.get("adx")
    ema_20 = holding.get("ema_20")
    ema_50 = holding.get("ema_50")
    ema_200 = holding.get("ema_200")
    rsi_history = holding.get("_rsi_history", [])
    volume_ratio = holding.get("volume_ratio")

    if price is None or rsi is None:
        return 0, []

    # Price below EMA-200 (trend broken) — strongest signal
    if ema_200 is not None and price < ema_200:
        score += 15
        signals.append(f"Price ({price}) below 200-EMA ({ema_200}) — long-term trend broken")

    # RSI overbought — take profits
    if rsi > SELL_RSI_OVERBOUGHT:
        score += 10
        signals.append(f"RSI={rsi:.1f} overbought (>{SELL_RSI_OVERBOUGHT}) — consider taking profits")

    # RSI momentum failure
    elif rsi < SELL_RSI_MOMENTUM_FAILED and len(rsi_history) >= 2:
        was_above_50 = any(v >= 50 for v in rsi_history[:-1])
        if was_above_50:
            score += 8
            signals.append(
                f"RSI={rsi:.1f} momentum failed (fell below {SELL_RSI_MOMENTUM_FAILED} "
                f"after being above 50)"
            )

    # ADX weak and falling
    if adx is not None and adx < SELL_ADX_WEAK:
        score += 7
        signals.append(f"ADX={adx:.1f} below {SELL_ADX_WEAK} — trend weakening")

    # Price below EMA-50
    if ema_50 is not None and price < ema_50:
        score += 5
        signals.append(f"Price ({price}) below 50-EMA ({ema_50}) — intermediate trend lost")

    # Price below EMA-20
    if ema_20 is not None and price < ema_20:
        score += 3
        signals.append(f"Price ({price}) below 20-EMA ({ema_20}) — short-term trend weak")

    # Volume deterioration
    if volume_ratio is not None and volume_ratio < SELL_VOLUME_DRY_RATIO:
        if ema_50 is not None and price >= ema_50 * 0.98:
            score += 8
            signals.append(
                f"Volume drying up: 5d/20d ratio={volume_ratio:.2f} (<{SELL_VOLUME_DRY_RATIO}) "
                f"while price near highs — possible distribution"
            )
        else:
            score += 4
            signals.append(
                f"Volume low: 5d/20d ratio={volume_ratio:.2f} — weak buying interest"
            )

    return min(score, 38), signals


def _score_relative_weakness(holding: dict) -> tuple[int, list[str]]:
    """Score 0-25 based on underperformance vs Nifty and sector."""
    score = 0
    signals = []

    stock_3m = holding.get("stock_3m_return")
    nifty_3m = holding.get("nifty_3m_return")
    sector_3m = holding.get("sector_3m_return")

    if stock_3m is None or nifty_3m is None:
        return 0, []

    nifty_gap = stock_3m - nifty_3m
    if nifty_gap <= SELL_RS_NIFTY_GAP:
        score += 12
        signals.append(
            f"3M return {stock_3m:.1f}% underperforms Nifty {nifty_3m:.1f}% "
            f"by {abs(nifty_gap):.1f}% — significant laggard"
        )
    elif nifty_gap <= -5.0:
        score += 7
        signals.append(
            f"3M return {stock_3m:.1f}% underperforms Nifty {nifty_3m:.1f}% by {abs(nifty_gap):.1f}%"
        )
    elif nifty_gap <= -2.0:
        score += 4
        signals.append(
            f"3M return {stock_3m:.1f}% slightly below Nifty {nifty_3m:.1f}%"
        )

    if sector_3m is not None:
        sector_gap = stock_3m - sector_3m
        if sector_gap <= SELL_RS_SECTOR_GAP:
            score += 13
            signals.append(
                f"3M return underperforms sector by {abs(sector_gap):.1f}% — sector laggard"
            )
        elif sector_gap <= -5.0:
            score += 8
            signals.append(
                f"3M return underperforms sector by {abs(sector_gap):.1f}%"
            )

    return min(score, 25), signals


def _score_fundamental_flags(holding: dict) -> tuple[int, list[str]]:
    """Score 0-25 based on fundamental deterioration."""
    score = 0
    signals = []

    decline_quarters = holding.get("profit_declining_quarters", 0) or 0
    qoq_declining = holding.get("qoq_declining", False)
    yoy_declining = holding.get("yoy_declining")
    roe = holding.get("roe")
    de = holding.get("debt_to_equity")

    # Consecutive quarterly profit decline
    if decline_quarters >= SELL_PROFIT_DECLINE_QUARTERS:
        score += 15
        signals.append(
            f"Profit declining for {decline_quarters} consecutive quarters — earnings deteriorating"
        )
    elif qoq_declining:
        score += 7
        signals.append("Quarterly profit fell QoQ — monitor for trend reversal")

    # YoY profit declining
    if yoy_declining is True:
        score += 10
        signals.append("Annual profit declining YoY — fundamental weakness")

    # ROE weakness
    if roe is not None:
        if roe < SELL_ROE_WEAK:
            score += 8
            signals.append(f"ROE={roe:.1f}% below {SELL_ROE_WEAK}% — poor capital efficiency")
        elif roe < SELL_ROE_MODERATE:
            score += 4
            signals.append(f"ROE={roe:.1f}% is marginal ({SELL_ROE_WEAK}–{SELL_ROE_MODERATE}%)")

    # High debt
    if de is not None and de > SELL_DE_HIGH:
        score += 7
        signals.append(f"D/E={de:.2f} — high leverage risk")

    return min(score, 25), signals


def _score_position_health(holding: dict) -> tuple[int, list[str]]:
    """Score 0-20 based on unrealized P&L position."""
    score = 0
    signals = []

    pnl_pct = holding.get("pnl_percentage", 0.0) or 0.0

    if pnl_pct < SELL_PNL_DEEP_LOSS_THRESHOLD:
        score = 20
        signals.append(
            f"Deep loss: {pnl_pct:.1f}% below entry — stop-loss review needed"
        )
    elif pnl_pct < SELL_PNL_LOSS_THRESHOLD:
        score = 14
        signals.append(f"Significant loss: {pnl_pct:.1f}% below entry")
    elif pnl_pct < -5.0:
        score = 8
        signals.append(f"Moderate loss: {pnl_pct:.1f}% below entry")
    elif pnl_pct < -2.0:
        score = 4
        signals.append(f"Minor loss: {pnl_pct:.1f}% below entry")

    return score, signals


def compute_sell_scores(
    holdings: list[dict],
    log: Callable[[str], None] = print,
    session: Optional[PipelineSession] = None,
) -> list[dict]:
    """Compute sell_urgency_score (0-100) and sell_signals for each holding.

    Sorts results by sell_urgency_score descending (most urgent to exit first).
    """
    for h in holdings:
        tech_score, tech_signals = _score_technical_breakdown(h)
        rs_score, rs_signals = _score_relative_weakness(h)
        fund_score, fund_signals = _score_fundamental_flags(h)
        pos_score, pos_signals = _score_position_health(h)

        total = min(100, tech_score + rs_score + fund_score + pos_score)
        all_signals = tech_signals + rs_signals + fund_signals + pos_signals

        if total >= SELL_URGENCY_STRONG:
            label = "STRONG SELL"
        elif total >= SELL_URGENCY_SELL:
            label = "SELL"
        elif total >= SELL_URGENCY_WATCH:
            label = "WATCH"
        else:
            label = "HOLD"

        h["sell_urgency_score"] = total
        h["sell_urgency_label"] = label
        h["sell_signals"] = all_signals
        h["sell_score_breakdown"] = {
            "technical_breakdown": tech_score,
            "relative_weakness": rs_score,
            "fundamental_flags": fund_score,
            "position_health": pos_score,
        }

    holdings.sort(key=lambda x: x.get("sell_urgency_score", 0), reverse=True)

    counts = {
        "STRONG SELL": sum(1 for h in holdings if h["sell_urgency_label"] == "STRONG SELL"),
        "SELL": sum(1 for h in holdings if h["sell_urgency_label"] == "SELL"),
        "WATCH": sum(1 for h in holdings if h["sell_urgency_label"] == "WATCH"),
        "HOLD": sum(1 for h in holdings if h["sell_urgency_label"] == "HOLD"),
    }
    log(
        f"Scored {len(holdings)} holdings — "
        f"STRONG SELL: {counts['STRONG SELL']}, SELL: {counts['SELL']}, "
        f"WATCH: {counts['WATCH']}, HOLD: {counts['HOLD']}"
    )
    return holdings


# ---------------------------------------------------------------------------
# Stage 5b: AI Ranking
# ---------------------------------------------------------------------------

def ai_rank_sell_candidates(
    holdings: list[dict],
    market_regime: dict,
    log: Callable[[str], None] = print,
    llm_provider: Optional[str] = None,
    user_id: Optional[int] = None,
    session: Optional[PipelineSession] = None,
) -> list[dict]:
    """LLM-powered sell reasoning per holding.

    Always uses Claude with extended thinking for sell analysis.
    Adds fields:
        sell_ai_conviction (1-10; 10 = strongest sell signal),
        sell_reason (one sentence why to exit),
        hold_reason (one sentence bull case against selling),
        news_sentiment (1-5), news_flag ('warning'|'clear'), news_headlines
    """
    from agents.config import get_llm

    llm = get_llm(
        temperature=0.1,
        provider="claude",
        extended_thinking=True,
        thinking_budget=CLAUDE_CONVICTION_THINKING_BUDGET,
        user_id=user_id,
        pipeline="sell",
    )

    # Fetch news for all holdings in parallel
    symbols = [h["symbol"] for h in holdings]
    news_map = fetch_news_batch(symbols, log=log)
    log("News fetched. Sending to LLM for sell reasoning...")

    vix = market_regime.get("vix", "N/A")
    regime = market_regime.get("regime", "normal")

    holding_lines = []
    for h in holdings:
        headlines = news_map.get(h["symbol"], [])
        headline_text = "; ".join([x["title"] for x in headlines[:5]]) or "No recent news"
        signals_text = "; ".join(h.get("sell_signals", [])) or "No signals triggered"

        holding_lines.append(
            f"- {h['symbol']}: UrgencyScore={h.get('sell_urgency_score')}, "
            f"Label={h.get('sell_urgency_label')}, Price={h.get('current_price')}, "
            f"RSI={h.get('rsi')}, ADX={h.get('adx')}, "
            f"EMA200={'below' if h.get('ema_200') and h.get('current_price') and h['current_price'] < h['ema_200'] else 'above'}, "
            f"3M Return={h.get('stock_3m_return')}% vs Nifty {h.get('nifty_3m_return')}%, "
            f"P&L={h.get('pnl_percentage')}%, ROE={h.get('roe', 'N/A')}, D/E={h.get('debt_to_equity', 'N/A')}, "
            f"Declining Quarters={h.get('profit_declining_quarters', 0)}, "
            f"Signals: [{signals_text}], "
            f"News: {headline_text}"
        )

    prompt = (
        "You are a senior portfolio risk analyst reviewing a user's Indian NSE stock holdings for potential exits.\n\n"
        f"Market Context:\n"
        f"- India VIX: {vix} (Regime: {regime})\n"
        f"- {len(holdings)} portfolio holdings being reviewed\n\n"
        f"Holdings Data (sorted by algorithmic sell urgency):\n"
        + "\n".join(holding_lines)
        + "\n\nFor EACH holding, provide a JSON object with these exact keys:\n"
        "{\n"
        '  "symbol": "<symbol>",\n'
        '  "sell_conviction": <integer 1-10, where 10=strongest sell signal, 1=should definitely hold>,\n'
        '  "sell_reason": "<one sentence max 25 words explaining why to exit this position>",\n'
        '  "hold_reason": "<one sentence max 20 words — the bull case for staying in>",\n'
        '  "news_sentiment": <integer 1-5, 1=very negative, 3=neutral, 5=very positive>,\n'
        '  "news_flag": "warning" | "clear"\n'
        "}\n\n"
        "Consider: technical signals, fundamental trends, news, sector momentum, P&L position, and market regime.\n"
        "A holding with a high algorithmic urgency score should generally receive a higher sell_conviction.\n\n"
        "Return ONLY a JSON array of these objects, no markdown, no extra text."
    )

    try:
        from agents.output_schemas import SellAnalysis
        from pydantic import ValidationError
        from services.cache_service import llm_cache_key, cache_get, cache_set

        _llm_cache_key = llm_cache_key("sell", prompt)
        _cached = cache_get(_llm_cache_key)
        if _cached:
            content = _cached.decode("utf-8")
            log("Sell AI: using cached LLM response")
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

        ranking_map: dict[str, SellAnalysis] = {}
        for item in raw_rankings:
            try:
                validated = SellAnalysis.model_validate(item)
                ranking_map[validated.symbol] = validated
            except ValidationError as ve:
                log(f"  Sell AI: validation warning for {item.get('symbol', '?')}: {ve.error_count()} error(s) — using defaults")

        for h in holdings:
            rank_data = ranking_map.get(h["symbol"])
            if rank_data:
                h["sell_ai_conviction"] = rank_data.sell_conviction
                h["sell_reason"] = rank_data.sell_reason
                h["hold_reason"] = rank_data.hold_reason
                h["news_sentiment"] = rank_data.news_sentiment
                h["news_flag"] = rank_data.news_flag
            else:
                score = h.get("sell_urgency_score", 0)
                h["sell_ai_conviction"] = max(1, min(10, score // 10))
                h["sell_reason"] = "; ".join(h.get("sell_signals", [])[:2]) or "Review required"
                h["hold_reason"] = "Insufficient AI data — review manually"
                h["news_sentiment"] = 3
                h["news_flag"] = "clear"
            h["news_headlines"] = [x["title"] for x in news_map.get(h["symbol"], [])[:3]]

        log(f"AI sell analysis complete for {len(holdings)} holdings")

    except Exception as e:
        log(f"AI sell analysis failed: {e}. Using default values.")
        for h in holdings:
            score = h.get("sell_urgency_score", 0)
            h["sell_ai_conviction"] = max(1, min(10, score // 10))
            h["sell_reason"] = "; ".join(h.get("sell_signals", [])[:2]) or "Review required"
            h["hold_reason"] = "Insufficient AI data — review manually"
            h["news_sentiment"] = 3
            h["news_flag"] = "clear"
            h["news_headlines"] = [x["title"] for x in news_map.get(h["symbol"], [])[:3]]

    return holdings
