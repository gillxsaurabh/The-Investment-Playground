"""Sell Analysis Tools — Portfolio audit pipeline.

Analyzes the user's current portfolio holdings for sell urgency.
Unlike the buy pipeline (which scans universe CSVs and filters down),
this pipeline starts with actual holdings and scores ALL of them —
no holdings are eliminated, every one receives a sell urgency score.

Stages:
  1. fetch_portfolio_holdings      — fetch live holdings + resolve tokens + sector lookup
  2. enrich_holdings_with_technicals  — RSI, ADX, EMA-20/50/200, ATR, 3M RS
  3. enrich_holdings_with_fundamentals — quarterly profit trend, ROE, D/E from Screener.in
  4. enrich_holdings_with_sector       — 5-day sector index performance
  5. compute_sell_scores + ai_rank_sell_candidates — urgency score + LLM reasoning
"""

import json
import time
import threading
from datetime import datetime, timedelta
from typing import Callable, Optional

import pandas as pd
import requests
from bs4 import BeautifulSoup
from concurrent.futures import ThreadPoolExecutor, as_completed

from broker import get_broker
from config import DATA_DIR
from constants import (
    SECTOR_HISTORY_CALENDAR_DAYS,
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

_DATA_DIR = DATA_DIR

# Module-level session caches (reset per pipeline run)
_sell_session_cache: dict[int, pd.DataFrame] = {}   # instrument_token → OHLCV DF
_sell_nifty_cache: Optional[pd.DataFrame] = None
_sell_sector_index_cache: dict[str, pd.DataFrame] = {}
_sell_instrument_map: Optional[dict[str, int]] = None

# Combined symbol → sector lookup (built from all universe CSVs)
_SELL_SYMBOL_SECTOR_MAP: dict[str, dict] = {}    # symbol → {sector, sector_index}


def clear_sell_session_cache():
    """Call at the start of each sell pipeline run."""
    global _sell_session_cache, _sell_nifty_cache, _sell_sector_index_cache
    global _sell_instrument_map, _SELL_SYMBOL_SECTOR_MAP
    _sell_session_cache = {}
    _sell_nifty_cache = None
    _sell_sector_index_cache = {}
    _sell_instrument_map = None
    _SELL_SYMBOL_SECTOR_MAP = {}


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _load_sector_indices() -> dict:
    json_path = _DATA_DIR / "sector_indices.json"
    with open(json_path) as f:
        return json.load(f)


def _build_symbol_sector_map(log: Callable = print) -> dict[str, dict]:
    """Build a combined symbol → {sector, sector_index} map from all universe CSVs."""
    global _SELL_SYMBOL_SECTOR_MAP
    if _SELL_SYMBOL_SECTOR_MAP:
        return _SELL_SYMBOL_SECTOR_MAP

    universe_files = [
        "nifty100.csv", "nifty500.csv",
        "nifty_midcap150.csv", "nifty_smallcap250.csv",
    ]
    for fname in universe_files:
        path = _DATA_DIR / fname
        if not path.exists():
            continue
        try:
            df = pd.read_csv(path)
            for _, row in df.iterrows():
                sym = row.get("symbol")
                if sym and sym not in _SELL_SYMBOL_SECTOR_MAP:
                    _SELL_SYMBOL_SECTOR_MAP[sym] = {
                        "sector": row.get("sector", "Unknown"),
                        "sector_index": row.get("sector_index"),
                    }
        except Exception as e:
            log(f"Warning: could not load {fname}: {e}")

    log(f"Loaded sector map with {len(_SELL_SYMBOL_SECTOR_MAP)} symbols")
    return _SELL_SYMBOL_SECTOR_MAP


def _resolve_sell_tokens(kite, log: Callable = print) -> dict[str, int]:
    """Fetch and cache NSE instrument tokens for sell pipeline."""
    global _sell_instrument_map
    if _sell_instrument_map is not None:
        return _sell_instrument_map
    log("Fetching NSE instrument list from Kite API...")
    instruments = kite.instruments("NSE")
    _sell_instrument_map = {}
    for inst in instruments:
        sym = inst.get("tradingsymbol")
        token = inst.get("instrument_token")
        if sym and token:
            _sell_instrument_map[sym] = token
    log(f"Loaded {len(_sell_instrument_map)} NSE instrument tokens")
    return _sell_instrument_map


def _fetch_sell_historical(kite, instrument_token: int, symbol: str,
                           days: int = SELL_HISTORICAL_DAYS) -> Optional[pd.DataFrame]:
    """Fetch daily OHLCV for a holding. Results cached in _sell_session_cache."""
    if instrument_token in _sell_session_cache:
        return _sell_session_cache[instrument_token]
    try:
        to_date = datetime.now()
        from_date = to_date - timedelta(days=days)
        history = kite.historical_data(
            instrument_token,
            from_date.strftime("%Y-%m-%d"),
            to_date.strftime("%Y-%m-%d"),
            "day",
        )
        if not history:
            return None
        df = pd.DataFrame(history)
        df["date"] = pd.to_datetime(df["date"], utc=True).dt.tz_localize(None)
        df.set_index("date", inplace=True)
        df.rename(columns={
            "open": "Open", "high": "High", "low": "Low",
            "close": "Close", "volume": "Volume",
        }, inplace=True)
        _sell_session_cache[instrument_token] = df
        return df
    except Exception as e:
        err = str(e)
        if "permission" in err.lower() or "Insufficient" in err:
            print(f"[SellPipeline] Permission error for {symbol}: {err}")
        else:
            print(f"[SellPipeline] Historical fetch failed for {symbol}: {err}")
        return None


def _fetch_sell_nifty(kite) -> Optional[pd.DataFrame]:
    """Fetch Nifty 50 historical data (cached per session)."""
    global _sell_nifty_cache
    if _sell_nifty_cache is not None:
        return _sell_nifty_cache
    _sell_nifty_cache = _fetch_sell_historical(kite, 256265, "NIFTY50", days=SELL_HISTORICAL_DAYS)
    return _sell_nifty_cache


def _calculate_ema(series: pd.Series, span: int) -> pd.Series:
    return series.ewm(span=span, adjust=False).mean()


def _calculate_rsi(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """Thin wrapper around the canonical RSI in services/technical.py."""
    from services.technical import calculate_rsi as _canonical_rsi
    return _canonical_rsi(df["Close"], period=period)


def _calculate_adx(df: pd.DataFrame, period: int = 14) -> Optional[float]:
    try:
        from services.technical import calculate_adx
        return calculate_adx(df, period)
    except Exception:
        return None


def _calculate_atr(df: pd.DataFrame, period: int = 14) -> Optional[float]:
    """Average True Range."""
    try:
        high = df["High"]
        low = df["Low"]
        prev_close = df["Close"].shift(1)
        tr = pd.concat([
            high - low,
            (high - prev_close).abs(),
            (low - prev_close).abs(),
        ], axis=1).max(axis=1)
        atr = tr.rolling(window=period).mean().iloc[-1]
        return round(float(atr), 2) if not pd.isna(atr) else None
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Stage 1: Fetch Portfolio Holdings
# ---------------------------------------------------------------------------

def fetch_portfolio_holdings(
    access_token: str,
    log: Callable[[str], None] = print,
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
    token_map = _resolve_sell_tokens(kite, log)
    sector_map = _build_symbol_sector_map(log)

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

        # Normalise P&L fields from broker response
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
# Stage 2: Enrich with Technicals
# ---------------------------------------------------------------------------

def enrich_holdings_with_technicals(
    holdings: list[dict],
    kite,
    log: Callable[[str], None] = print,
) -> list[dict]:
    """Fetch OHLCV + compute indicators for each holding.

    Adds fields:
        current_price, rsi, adx, ema_20, ema_50, ema_200, atr,
        stock_3m_return, nifty_3m_return, avg_volume_20d, volume_ratio,
        rsi_history (last 15 RSI values for momentum detection — internal)

    Holdings that fail to fetch data still pass through (indicators will be None).
    """
    # Fetch Nifty benchmark
    nifty_df = _fetch_sell_nifty(kite)
    nifty_3m_return = 0.0
    if nifty_df is not None and len(nifty_df) >= 63:
        nifty_3m_return = (
            (nifty_df["Close"].iloc[-1] / nifty_df["Close"].iloc[-63]) - 1
        ) * 100
    log(f"Nifty 50 3M return: {nifty_3m_return:.2f}%")

    rate_lock = threading.Lock()
    enriched_count = [0]
    failed_count = [0]

    def enrich_one(holding: dict) -> dict:
        symbol = holding["symbol"]
        token = holding["instrument_token"]

        with rate_lock:
            time.sleep(0.35)  # Rate limiting

        df = _fetch_sell_historical(kite, token, symbol)
        if df is None or len(df) < 30:
            with rate_lock:
                failed_count[0] += 1
            log(f"  {symbol}: data unavailable — keeping with null indicators")
            holding.update({
                "current_price": holding.get("last_price"),
                "rsi": None, "adx": None,
                "ema_20": None, "ema_50": None, "ema_200": None,
                "atr": None, "stock_3m_return": None,
                "nifty_3m_return": round(nifty_3m_return, 2),
                "avg_volume_20d": None, "volume_ratio": None,
                "_rsi_history": [],
            })
            return holding

        current_price = round(float(df["Close"].iloc[-1]), 2)
        ema_20 = round(float(_calculate_ema(df["Close"], 20).iloc[-1]), 2)
        ema_50 = round(float(_calculate_ema(df["Close"], 50).iloc[-1]), 2)
        ema_200_val = _calculate_ema(df["Close"], 200).iloc[-1]
        ema_200 = round(float(ema_200_val), 2) if not pd.isna(ema_200_val) else None

        rsi_series = _calculate_rsi(df)
        rsi = round(float(rsi_series.iloc[-1]), 2) if not rsi_series.empty else None
        # Keep recent RSI history for momentum-failure detection
        rsi_history = [round(float(v), 2) for v in rsi_series.dropna().tail(SELL_MOMENTUM_LOOKBACK + 2).tolist()]

        adx = _calculate_adx(df)
        atr = _calculate_atr(df)

        avg_volume_20d = round(float(df["Volume"].tail(20).mean()), 0)
        avg_volume_5d = df["Volume"].tail(5).mean()
        volume_ratio = round(float(avg_volume_5d / avg_volume_20d), 2) if avg_volume_20d > 0 else 1.0

        stock_3m_return = None
        if len(df) >= 63:
            stock_3m_return = round(
                ((current_price / float(df["Close"].iloc[-63])) - 1) * 100, 2
            )

        with rate_lock:
            enriched_count[0] += 1

        log(
            f"  {symbol}: price={current_price}, RSI={rsi}, ADX={adx}, "
            f"EMA200={'below' if ema_200 and current_price < ema_200 else 'above'}"
        )

        holding.update({
            "current_price": current_price,
            "rsi": rsi,
            "adx": adx,
            "ema_20": ema_20,
            "ema_50": ema_50,
            "ema_200": ema_200,
            "atr": atr,
            "stock_3m_return": stock_3m_return,
            "nifty_3m_return": round(nifty_3m_return, 2),
            "avg_volume_20d": avg_volume_20d,
            "volume_ratio": volume_ratio,
            "_rsi_history": rsi_history,  # internal — stripped before final output
        })
        return holding

    log(f"Fetching OHLCV and computing indicators for {len(holdings)} holdings...")
    results = []
    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = {executor.submit(enrich_one, h): h["symbol"] for h in holdings}
        for future in as_completed(futures):
            results.append(future.result())

    log(f"Technical scan complete: {enriched_count[0]} enriched, {failed_count[0]} data unavailable")
    return results


# ---------------------------------------------------------------------------
# Stage 3: Enrich with Fundamentals
# ---------------------------------------------------------------------------

_SCREENER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
}


def _parse_number(text: str) -> Optional[float]:
    try:
        cleaned = text.strip().replace(",", "").replace("%", "")
        if not cleaned or cleaned == "--":
            return None
        return float(cleaned)
    except (ValueError, AttributeError):
        return None


def _scrape_sell_fundamentals(symbol: str) -> dict:
    """Scrape Screener.in for quarterly profits, ROE, D/E.

    Returns dict with:
        profit_values: list of quarterly profits (oldest first)
        roe: float or None
        debt_to_equity: float or None
        consecutive_decline_quarters: int (0 if stable/growing)
        qoq_declining: bool
        yoy_declining: bool or None
    """
    result = {
        "profit_values": [],
        "roe": None,
        "debt_to_equity": None,
        "consecutive_decline_quarters": 0,
        "qoq_declining": False,
        "yoy_declining": None,
    }

    try:
        time.sleep(1.0)
        url = f"https://www.screener.in/company/{symbol}/consolidated/"
        resp = requests.get(url, headers=_SCREENER_HEADERS, timeout=15)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.content, "html.parser")

        # --- Quarterly profits ---
        for section in soup.find_all("section"):
            heading = section.find(["h2", "h3"])
            if not heading or "quarter" not in heading.get_text().lower():
                continue
            table = section.find("table")
            if not table:
                continue
            for row in table.find_all("tr"):
                cells = row.find_all(["th", "td"])
                if not cells:
                    continue
                label = cells[0].get_text().strip().lower()
                if "net profit" in label or "profit after tax" in label:
                    values = [_parse_number(c.get_text()) for c in cells[1:]]
                    values = [v for v in values if v is not None]
                    result["profit_values"] = values
                    if len(values) >= 2:
                        result["qoq_declining"] = values[-1] < values[-2]
                    if len(values) >= 5:
                        result["yoy_declining"] = values[-1] < values[-5]

                    # Count consecutive declining quarters
                    decline_count = 0
                    for i in range(len(values) - 1, 0, -1):
                        if values[i] < values[i - 1]:
                            decline_count += 1
                        else:
                            break
                    result["consecutive_decline_quarters"] = decline_count
                    break
            break

        # --- Ratios (ROE, D/E) from key ratios section ---
        try:
            from services.fundamentals import scrape_screener_ratios
            ratios = scrape_screener_ratios(symbol)
            result["roe"] = ratios.get("roe")
            result["debt_to_equity"] = ratios.get("debt_to_equity")
        except Exception:
            # Fallback: parse from same page
            for li in soup.find_all("li", class_=lambda c: c and "flex" in c):
                text = li.get_text(separator=" ").strip()
                if "Return on equity" in text or "ROE" in text:
                    for span in li.find_all("span"):
                        val = _parse_number(span.get_text())
                        if val is not None:
                            result["roe"] = val
                            break

    except Exception as e:
        print(f"[SellPipeline] Screener.in failed for {symbol}: {e}")

    return result


def enrich_holdings_with_fundamentals(
    holdings: list[dict],
    log: Callable[[str], None] = print,
) -> list[dict]:
    """Scrape Screener.in for each holding's fundamental health.

    Adds fields:
        roe, debt_to_equity, profit_declining_quarters (consecutive),
        qoq_declining, yoy_declining
    """
    log(f"Scraping Screener.in for {len(holdings)} holdings (1s rate limit)...")
    enriched = [0]

    def enrich_one(holding: dict) -> dict:
        symbol = holding["symbol"]
        data = _scrape_sell_fundamentals(symbol)

        holding["roe"] = data.get("roe")
        holding["debt_to_equity"] = data.get("debt_to_equity")
        holding["profit_declining_quarters"] = data.get("consecutive_decline_quarters", 0)
        holding["qoq_declining"] = data.get("qoq_declining", False)
        holding["yoy_declining"] = data.get("yoy_declining")

        decline_q = holding["profit_declining_quarters"]
        roe_str = f"ROE={holding['roe']:.1f}%" if holding["roe"] is not None else "ROE=N/A"
        log(
            f"  {symbol}: {roe_str}, D/E={holding.get('debt_to_equity', 'N/A')}, "
            f"consecutive declining quarters={decline_q}, QoQ declining={holding['qoq_declining']}"
        )
        enriched[0] += 1
        return holding

    results = []
    with ThreadPoolExecutor(max_workers=3) as executor:
        futures = {executor.submit(enrich_one, h): h["symbol"] for h in holdings}
        for future in as_completed(futures):
            results.append(future.result())

    log(f"Fundamentals scan complete: {enriched[0]} / {len(holdings)} processed")
    return results


# ---------------------------------------------------------------------------
# Stage 4: Enrich with Sector Performance
# ---------------------------------------------------------------------------

def enrich_holdings_with_sector(
    holdings: list[dict],
    access_token: str,
    log: Callable[[str], None] = print,
) -> list[dict]:
    """Add 5-day sector index return to each holding.

    Does NOT filter — all holdings pass through, some may have sector_5d_change=0.0
    if sector data is unavailable.
    """
    broker = get_broker(access_token)
    kite = broker.raw_kite

    # Collect unique sector indices
    needed = set()
    for h in holdings:
        si = h.get("sector_index")
        if si:
            needed.add(si)

    if not needed:
        log("No sector indices found for holdings — skipping sector enrichment")
        for h in holdings:
            h["sector_5d_change"] = None
        return holdings

    # Resolve sector index tokens (use _sell_instrument_map if already loaded)
    global _sell_instrument_map
    if _sell_instrument_map is None:
        _sell_instrument_map = {}
        instruments = kite.instruments("NSE")
        for inst in instruments:
            sym = inst.get("tradingsymbol")
            token = inst.get("instrument_token")
            if sym and token:
                _sell_instrument_map[sym] = token

    sector_token_map: dict[str, int] = {}
    sector_indices = _load_sector_indices()
    for _, idx_symbol in sector_indices.items():
        ts = idx_symbol.replace("NSE:", "")
        token = _sell_instrument_map.get(ts)
        if token:
            sector_token_map[idx_symbol] = token

    # Fetch 5-day change AND 3-month return per sector index
    # Use 90 calendar days to get enough trading days for 3M comparison
    sector_change: dict[str, float] = {}
    sector_3m: dict[str, float] = {}
    for idx_symbol in needed:
        token = sector_token_map.get(idx_symbol)
        if not token:
            log(f"  No token for {idx_symbol}, defaulting to 0.0")
            sector_change[idx_symbol] = 0.0
            sector_3m[idx_symbol] = 0.0
            continue
        try:
            to_date = datetime.now()
            from_date = to_date - timedelta(days=90)  # 90 days covers both 5d and 3M
            history = kite.historical_data(
                token,
                from_date.strftime("%Y-%m-%d"),
                to_date.strftime("%Y-%m-%d"),
                "day",
            )
            if history and len(history) >= 5:
                recent = history[-1]["close"]
                five_days_ago = history[-5]["close"]
                pct = ((recent - five_days_ago) / five_days_ago * 100) if five_days_ago > 0 else 0.0
                sector_change[idx_symbol] = round(pct, 2)
            elif history and len(history) >= 2:
                pct = ((history[-1]["close"] - history[0]["close"]) / history[0]["close"]) * 100
                sector_change[idx_symbol] = round(pct, 2)
            else:
                sector_change[idx_symbol] = 0.0

            # 3-month sector return: use up to 63 trading days back
            if history and len(history) >= 63:
                pct_3m = ((history[-1]["close"] - history[-63]["close"]) / history[-63]["close"]) * 100
                sector_3m[idx_symbol] = round(pct_3m, 2)
            elif history and len(history) >= 2:
                pct_3m = ((history[-1]["close"] - history[0]["close"]) / history[0]["close"]) * 100
                sector_3m[idx_symbol] = round(pct_3m, 2)
            else:
                sector_3m[idx_symbol] = 0.0

            time.sleep(0.35)
        except Exception as e:
            log(f"  Sector history failed for {idx_symbol}: {e}")
            sector_change[idx_symbol] = 0.0
            sector_3m[idx_symbol] = 0.0

    log(f"Sector 5-day changes: {json.dumps(sector_change)}")
    log(f"Sector 3M returns: {json.dumps(sector_3m)}")

    for h in holdings:
        si = h.get("sector_index")
        h["sector_5d_change"] = sector_change.get(si, 0.0) if si else None
        h["sector_3m_return"] = sector_3m.get(si, 0.0) if si else None

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
    volume_ratio = holding.get("volume_ratio")  # 5d / 20d avg volume

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

    # RSI momentum failure — was above 50, now below SELL_RSI_MOMENTUM_FAILED
    elif rsi < SELL_RSI_MOMENTUM_FAILED and len(rsi_history) >= 2:
        # Check if RSI was above 50 within the lookback window
        was_above_50 = any(v >= 50 for v in rsi_history[:-1])
        if was_above_50:
            score += 8
            signals.append(
                f"RSI={rsi:.1f} momentum failed (fell below {SELL_RSI_MOMENTUM_FAILED} "
                f"after being above 50)"
            )

    # ADX weak and falling
    if adx is not None and adx < SELL_ADX_WEAK:
        # Check if ADX is falling (compare last 5 days if data available)
        adx_falling = True  # We only have current ADX scalar; flag as weak
        if adx_falling:
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

    # Volume deterioration — distribution signal:
    # Volume drying up while price is near EMA-50 or above suggests institutions are quietly exiting
    if volume_ratio is not None and volume_ratio < SELL_VOLUME_DRY_RATIO:
        if ema_50 is not None and price >= ema_50 * 0.98:
            # Price still near/above support but volume collapsing = distribution
            score += 8
            signals.append(
                f"Volume drying up: 5d/20d ratio={volume_ratio:.2f} (<{SELL_VOLUME_DRY_RATIO}) "
                f"while price near highs — possible distribution"
            )
        else:
            # Price already weak + low volume = lack of buying interest
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
    # Positive P&L: score = 0 (sell signal must come from other dimensions)

    return score, signals


def compute_sell_scores(
    holdings: list[dict],
    log: Callable[[str], None] = print,
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

    # Sort by urgency descending
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

def _fetch_sell_news(symbol: str, days: int = NEWS_LOOKBACK_DAYS) -> list[dict]:
    """Fetch recent news from Google News RSS."""
    import xml.etree.ElementTree as ET
    from email.utils import parsedate_to_datetime
    try:
        url = f"https://news.google.com/rss/search?q={symbol}+NSE+stock&hl=en-IN&gl=IN&ceid=IN:en"
        resp = requests.get(url, headers={
            "User-Agent": "Mozilla/5.0 (compatible; CogniCap/1.0)"
        }, timeout=10)
        resp.raise_for_status()
        root = ET.fromstring(resp.content)
        cutoff = datetime.now() - timedelta(days=days)
        headlines = []
        for item in root.findall(".//item"):
            title_el = item.find("title")
            pub_el = item.find("pubDate")
            if title_el is None:
                continue
            title = title_el.text or ""
            if pub_el is not None and pub_el.text:
                try:
                    pub_date = parsedate_to_datetime(pub_el.text)
                    if pub_date.replace(tzinfo=None) < cutoff:
                        continue
                except Exception:
                    pass
            headlines.append({
                "title": title,
                "published": pub_el.text if pub_el is not None else None,
            })
            if len(headlines) >= 10:
                break
        return headlines
    except Exception as e:
        print(f"[SellPipeline] News fetch failed for {symbol}: {e}")
        return []


def ai_rank_sell_candidates(
    holdings: list[dict],
    market_regime: dict,
    log: Callable[[str], None] = print,
    llm_provider: Optional[str] = None,
    user_id: Optional[int] = None,
) -> list[dict]:
    """LLM-powered sell reasoning per holding.

    Default provider is Claude. Falls back to Gemini if Claude unavailable.
    Adds fields:
        sell_ai_conviction (1-10; 10 = strongest sell signal),
        sell_reason (one sentence why to exit),
        hold_reason (one sentence bull case against selling),
        news_sentiment (1-5), news_flag ('warning'|'clear'), news_headlines
    """
    from agents.config import get_llm

    # Default to Claude for sell pipeline
    effective_provider = llm_provider if llm_provider else "claude"

    if effective_provider == "claude":
        llm = get_llm(
            temperature=0.1,
            provider="claude",
            extended_thinking=True,
            thinking_budget=CLAUDE_CONVICTION_THINKING_BUDGET,
            user_id=user_id,
        )
    else:
        llm = get_llm(temperature=0.3, provider=effective_provider if effective_provider != "gemini" else None, user_id=user_id)

    # Fetch news for all holdings (threaded)
    log(f"Fetching news for {len(holdings)} holdings...")
    news_map: dict[str, list[dict]] = {}

    def fetch_news(symbol: str):
        return symbol, _fetch_sell_news(symbol)

    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = [executor.submit(fetch_news, h["symbol"]) for h in holdings]
        for future in as_completed(futures):
            sym, headlines = future.result()
            news_map[sym] = headlines

    log("News fetched. Sending to LLM for sell reasoning...")

    vix = market_regime.get("vix", "N/A")
    regime = market_regime.get("regime", "normal")

    # Build prompt
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
        response = llm.invoke(prompt)
        content = response.content.strip()
        if "```" in content:
            content = content.split("```")[1]
            if content.startswith("json"):
                content = content[4:]
            content = content.strip()
        rankings = json.loads(content)
        ranking_map = {r["symbol"]: r for r in rankings}

        for h in holdings:
            rank_data = ranking_map.get(h["symbol"], {})
            h["sell_ai_conviction"] = max(1, min(10, rank_data.get("sell_conviction", 5)))
            h["sell_reason"] = rank_data.get("sell_reason", "")
            h["hold_reason"] = rank_data.get("hold_reason", "")
            h["news_sentiment"] = max(1, min(5, rank_data.get("news_sentiment", 3)))
            h["news_flag"] = rank_data.get("news_flag", "clear")
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
