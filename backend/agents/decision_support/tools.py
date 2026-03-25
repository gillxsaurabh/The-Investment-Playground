"""Decision Support Tools — The "4-2-1-1" stock selection pipeline.

Tool 1: filter_market_universe — Volume, 200-EMA, relative strength vs Nifty
Tool 2: analyze_technicals     — 20-EMA, RSI entry triggers
Tool 3: check_fundamentals     — Quarterly profit growth from Screener.in
Tool 4: check_sector_health    — Sector index daily performance check

Data source: Kite Connect API only (no yfinance).
Indicators: Manual EMA/RSI calculations (no pandas_ta).
"""

import json
import os
import time
import threading
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Optional

import pandas as pd
import requests
from bs4 import BeautifulSoup
from kiteconnect import KiteConnect
from concurrent.futures import ThreadPoolExecutor, as_completed

from agents.decision_support.strategy_config import (
    DEFAULT_RSI_PERIOD,
    DEFAULT_RSI_BUY_LIMIT,
    DEFAULT_EMA_PERIOD,
    DEFAULT_MIN_TURNOVER,
)
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
)
from services.technical import calculate_adx, calculate_rsi as _canonical_rsi

# ---------------------------------------------------------------------------
# Module-level caches (cleared at the start of each pipeline run)
# ---------------------------------------------------------------------------
_session_cache: dict[int, pd.DataFrame] = {}   # instrument_token → historical DF
_nifty_cache: Optional[pd.DataFrame] = None
_sector_index_cache: dict[str, pd.DataFrame] = {}  # sector_index symbol → historical DF

_DATA_DIR = DATA_DIR

_universe_cache: dict[str, pd.DataFrame] = {}

# Map universe key → CSV filename
_UNIVERSE_FILES = {
    "nifty100": "nifty100.csv",
    "nifty500": "nifty500.csv",
    "nifty_midcap150": "nifty_midcap150.csv",
    "nifty_smallcap250": "nifty_smallcap250.csv",
}


def _load_universe(universe: str = "nifty500") -> pd.DataFrame:
    """Load a stock universe CSV (cached at module level).

    Args:
        universe: one of 'nifty100', 'nifty500', 'nifty_midcap150', 'nifty_smallcap250'.

    Raises:
        FileNotFoundError: if the requested universe CSV does not exist.
        ValueError: if the universe key is not recognized.
    """
    if universe in _universe_cache:
        return _universe_cache[universe]
    filename = _UNIVERSE_FILES.get(universe)
    if filename is None:
        raise ValueError(
            f"Unknown universe '{universe}'. "
            f"Valid options: {', '.join(_UNIVERSE_FILES.keys())}"
        )
    csv_path = _DATA_DIR / filename
    if not csv_path.exists():
        raise FileNotFoundError(
            f"Universe file not found: {csv_path}. "
            f"Run 'python scripts/generate_universe_csvs.py' to create it."
        )
    df = pd.read_csv(csv_path)
    _universe_cache[universe] = df
    return df


def _load_sector_indices() -> dict:
    """Load sector → index mapping."""
    json_path = _DATA_DIR / "sector_indices.json"
    with open(json_path) as f:
        return json.load(f)


def _get_kite(access_token: str) -> KiteConnect:
    broker = get_broker(access_token)
    return broker.raw_kite


# Cached instrument token lookup (symbol → token)
_instrument_map: Optional[dict[str, int]] = None


def _resolve_instrument_tokens(kite: KiteConnect, log: Callable = print) -> dict[str, int]:
    """Fetch real instrument tokens from Kite API. Cached per session."""
    global _instrument_map
    if _instrument_map is not None:
        return _instrument_map
    log("Fetching NSE instrument list from Kite API...")
    instruments = kite.instruments("NSE")
    _instrument_map = {}
    for inst in instruments:
        sym = inst.get("tradingsymbol")
        token = inst.get("instrument_token")
        if sym and token:
            _instrument_map[sym] = token
    log(f"Loaded {len(_instrument_map)} NSE instrument tokens")
    return _instrument_map


def clear_session_cache():
    """Call at the start of each pipeline run."""
    global _session_cache, _nifty_cache, _instrument_map, _universe_cache, _sector_index_cache
    _session_cache = {}
    _nifty_cache = None
    _instrument_map = None
    _universe_cache = {}
    _sector_index_cache = {}


# ---------------------------------------------------------------------------
# Helper: Fetch & cache historical data
# ---------------------------------------------------------------------------

def _fetch_historical(kite: KiteConnect, instrument_token: int, symbol: str,
                      days: int = 400) -> Optional[pd.DataFrame]:
    """Fetch daily OHLCV data from Kite. Results cached in _session_cache."""
    if instrument_token in _session_cache:
        return _session_cache[instrument_token]
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
        _session_cache[instrument_token] = df
        return df
    except Exception as e:
        err_msg = str(e)
        if "permission" in err_msg.lower() or "Insufficient" in err_msg:
            print(f"[DecisionSupport] Permission error for {symbol} — check API key has historical data add-on: {err_msg}")
        else:
            print(f"[DecisionSupport] Historical fetch failed for {symbol}: {err_msg}")
        return None


def _fetch_nifty(kite: KiteConnect) -> Optional[pd.DataFrame]:
    """Fetch Nifty 50 historical data (cached per session)."""
    global _nifty_cache
    if _nifty_cache is not None:
        return _nifty_cache
    _nifty_cache = _fetch_historical(kite, 256265, "NIFTY50", days=400)
    return _nifty_cache


# ---------------------------------------------------------------------------
# Indicator calculations
# ---------------------------------------------------------------------------

def _calculate_ema(series: pd.Series, span: int) -> pd.Series:
    return series.ewm(span=span, adjust=False).mean()


def _calculate_rsi(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """Thin wrapper around the canonical RSI in services/technical.py."""
    return _canonical_rsi(df["Close"], period=period)


# ---------------------------------------------------------------------------
# Tool 1: Universe Filter
# ---------------------------------------------------------------------------

def filter_market_universe(
    access_token: str,
    log: Callable[[str], None] = print,
    min_turnover: int = DEFAULT_MIN_TURNOVER,
    ema_period: int = DEFAULT_EMA_PERIOD,
    universe: str = "nifty500",
) -> list[dict]:
    """Filter stock universe: turnover, volume trend, 200-EMA, relative strength vs Nifty + sector.

    Returns list of stock dicts with keys:
        symbol, instrument_token, sector, sector_index, current_price,
        avg_volume_20d, avg_turnover_20d, ema_200, volume_ratio,
        stock_3m_return, nifty_3m_return, sector_3m_return
    """
    kite = _get_kite(access_token)
    stocks_df = _load_universe(universe)
    total = len(stocks_df)
    universe_label = universe.replace("_", " ").title()
    log(f"Loaded {universe_label} list: {total} stocks")

    # --- Step 1: Fetch Nifty 50 data for relative strength ----------------
    nifty_df = _fetch_nifty(kite)
    nifty_3m_return = 0.0
    if nifty_df is not None and len(nifty_df) >= 63:
        nifty_3m_return = (
            (nifty_df["Close"].iloc[-1] / nifty_df["Close"].iloc[-63]) - 1
        ) * 100
    log(f"Nifty 50 3-month return: {nifty_3m_return:.2f}%")

    # --- Step 2: Resolve real instrument tokens from Kite API -------------
    token_map = _resolve_instrument_tokens(kite, log)

    # --- Step 3: Pre-fetch sector index data for sector-relative strength --
    global _sector_index_cache
    sector_indices_needed: set[str] = set()
    for _, row in stocks_df.iterrows():
        si = row.get("sector_index")
        if si and pd.notna(si):
            sector_indices_needed.add(si)

    sector_token_map = _get_sector_index_tokens()
    for idx_symbol in sector_indices_needed:
        token = sector_token_map.get(idx_symbol)
        if token and idx_symbol not in _sector_index_cache:
            df = _fetch_historical(kite, token, idx_symbol, days=400)
            if df is not None:
                _sector_index_cache[idx_symbol] = df
            time.sleep(0.35)
    log(f"Pre-fetched {len(_sector_index_cache)} sector index histories for relative strength")

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

        df = _fetch_historical(kite, stock["instrument_token"], stock["symbol"], days=400)
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
        ema_val = _calculate_ema(df["Close"], ema_period).iloc[-1]
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
        if sector_idx and sector_idx in _sector_index_cache:
            sector_df = _sector_index_cache[sector_idx]
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

    # Diagnostic breakdown
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
) -> list[dict]:
    """Filter by EMA, ADX trend strength, and RSI entry triggers.

    Pullback trigger: Price > 200-EMA (relaxed, can be below 20-EMA) + RSI < rsi_buy_limit
    Momentum trigger: Price > 20-EMA + RSI crossed above 50 in last 5 days
    Both require: ADX >= ADX_PIPELINE_MIN (trend confirmation)

    Uses cached historical data from Tool 1 (no new API calls).
    """
    passed = []
    counters = {"no_data": 0, "adx_weak": 0, "no_trigger": 0, "passed": 0}

    for stock in stocks:
        token = stock["instrument_token"]
        df = _session_cache.get(token)
        if df is None or len(df) < 50:
            counters["no_data"] += 1
            continue

        current_price = df["Close"].iloc[-1]
        ema_20 = _calculate_ema(df["Close"], 20).iloc[-1]
        ema_200 = stock.get("ema_200") or _calculate_ema(df["Close"], 200).iloc[-1]

        # ADX trend strength gate
        adx_val = calculate_adx(df)
        if adx_val is None or pd.isna(adx_val) or adx_val < ADX_PIPELINE_MIN:
            counters["adx_weak"] += 1
            continue

        rsi_series = _calculate_rsi(df, 14)
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

_SCREENER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
}


def _parse_number(text: str) -> Optional[float]:
    """Parse a number string like '1,234.56' or '-456' from Screener.in."""
    try:
        cleaned = text.strip().replace(",", "").replace("%", "")
        if not cleaned or cleaned == "--":
            return None
        return float(cleaned)
    except (ValueError, AttributeError):
        return None


def _get_quarterly_profit_growth(symbol: str) -> Optional[bool]:
    """Scrape Screener.in for quarterly net profit. Returns True if growing."""
    try:
        time.sleep(1.0)  # Rate limit
        url = f"https://www.screener.in/company/{symbol}/consolidated/"
        resp = requests.get(url, headers=_SCREENER_HEADERS, timeout=15)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.content, "html.parser")

        # Find quarterly results section
        for section in soup.find_all("section"):
            heading = section.find(["h2", "h3"])
            if not heading:
                continue
            if "quarter" not in heading.get_text().lower():
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
                    if len(values) >= 2:
                        current_q = values[-1]
                        previous_q = values[-2]
                        return current_q > previous_q
        return None
    except Exception as e:
        print(f"[DecisionSupport] Screener.in failed for {symbol}: {e}")
        return None


def _get_latest_quarterly_profit(symbol: str) -> Optional[float]:
    """Scrape Screener.in for the latest quarterly net profit value."""
    try:
        time.sleep(1.0)
        url = f"https://www.screener.in/company/{symbol}/consolidated/"
        resp = requests.get(url, headers=_SCREENER_HEADERS, timeout=15)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.content, "html.parser")

        for section in soup.find_all("section"):
            heading = section.find(["h2", "h3"])
            if not heading:
                continue
            if "quarter" not in heading.get_text().lower():
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
                    if values:
                        return values[-1]
        return None
    except Exception as e:
        print(f"[DecisionSupport] Screener.in profit fetch failed for {symbol}: {e}")
        return None


def _get_quarterly_profit_yoy_growth(symbol: str) -> Optional[dict]:
    """Scrape Screener.in for quarterly profits and check YoY + QoQ growth.

    Returns dict with keys:
        yoy_growing: bool or None (None if < 5 quarters available)
        qoq_growing: bool
        current_q_profit: float
        yoy_q_profit: float or None
        previous_q_profit: float
    Returns None on complete failure.
    """
    try:
        time.sleep(1.0)
        url = f"https://www.screener.in/company/{symbol}/consolidated/"
        resp = requests.get(url, headers=_SCREENER_HEADERS, timeout=15)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.content, "html.parser")

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
                    if len(values) >= YOY_QUARTERS_NEEDED:
                        current_q = values[-1]
                        previous_q = values[-2]
                        yoy_q = values[-5]  # same quarter last year
                        return {
                            "yoy_growing": current_q > yoy_q,
                            "qoq_growing": current_q > previous_q,
                            "current_q_profit": current_q,
                            "yoy_q_profit": yoy_q,
                            "previous_q_profit": previous_q,
                        }
                    elif len(values) >= 2:
                        return {
                            "yoy_growing": None,
                            "qoq_growing": values[-1] > values[-2],
                            "current_q_profit": values[-1],
                            "yoy_q_profit": None,
                            "previous_q_profit": values[-2],
                        }
        return None
    except Exception as e:
        print(f"[DecisionSupport] YoY profit check failed for {symbol}: {e}")
        return None


def check_fundamentals(
    stocks: list[dict],
    log: Callable[[str], None] = print,
    fundamental_check: str = "standard",
) -> list[dict]:
    """Filter stocks based on fundamental health.

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

    passed = []
    failed_count = 0

    if fundamental_check == "loose":
        def check_one(stock: dict) -> Optional[dict]:
            profit = _get_latest_quarterly_profit(stock["symbol"])
            if profit is not None and profit > 0:
                stock["quarterly_profit_positive"] = True
                return stock
            return None

    elif fundamental_check == "strict":
        def check_one(stock: dict) -> Optional[dict]:
            # YoY/QoQ profit growth
            result = _get_quarterly_profit_yoy_growth(stock["symbol"])
            if result is None:
                return None
            if result["yoy_growing"] is True:
                stock["profit_yoy_growing"] = True
            elif result["yoy_growing"] is None and result["qoq_growing"] is True:
                stock["profit_yoy_growing"] = None  # YoY unavailable, QoQ passed
            else:
                return None
            stock["quarterly_profit_growth"] = True
            stock["profit_qoq_growing"] = result["qoq_growing"]

            # Additional: ROE > 15 AND D/E < 1.0
            from services.fundamentals import scrape_screener_ratios
            ratios = scrape_screener_ratios(stock["symbol"])
            roe = ratios.get("roe")
            de = ratios.get("debt_to_equity")
            if roe is None or roe < STRICT_ROE_MIN:
                return None
            if de is not None and de > STRICT_DE_MAX:
                return None
            stock["roe"] = roe
            stock["debt_to_equity"] = de
            return stock

    else:  # "standard"
        def check_one(stock: dict) -> Optional[dict]:
            result = _get_quarterly_profit_yoy_growth(stock["symbol"])
            if result is None:
                return None
            # Primary: YoY growth. Fallback: QoQ if YoY unavailable
            if result["yoy_growing"] is True:
                stock["profit_yoy_growing"] = True
            elif result["yoy_growing"] is None and result["qoq_growing"] is True:
                stock["profit_yoy_growing"] = None
            else:
                return None
            stock["quarterly_profit_growth"] = True
            stock["profit_qoq_growing"] = result["qoq_growing"]
            return stock

    with ThreadPoolExecutor(max_workers=3) as executor:
        futures = {executor.submit(check_one, s): s["symbol"] for s in stocks}
        done_count = 0
        for future in as_completed(futures):
            done_count += 1
            result = future.result()
            if result is not None:
                passed.append(result)
            else:
                failed_count += 1
            if done_count % 5 == 0:
                log(f"Fundamentals: {done_count} / {len(stocks)} checked")

    log(f"Fundamental filter ({fundamental_check}): {len(passed)} passed, {failed_count} failed/removed")
    return passed


# ---------------------------------------------------------------------------
# Tool 4: Sector Health Check
# ---------------------------------------------------------------------------

def _get_sector_index_tokens() -> dict[str, int]:
    """Map sector index symbols (e.g. 'NSE:NIFTY AUTO') to instrument tokens.

    Uses the already-loaded _instrument_map from the NSE instruments list.
    Sector indices are listed under tradingsymbol like 'NIFTY AUTO', 'NIFTY BANK', etc.
    """
    if _instrument_map is None:
        return {}
    sector_indices = _load_sector_indices()
    result: dict[str, int] = {}
    for sector_name, idx_symbol in sector_indices.items():
        # idx_symbol is like "NSE:NIFTY AUTO" — extract the tradingsymbol part
        ts = idx_symbol.replace("NSE:", "")
        token = _instrument_map.get(ts)
        if token:
            result[idx_symbol] = token
    return result


def check_sector_health(
    access_token: str,
    stocks: list[dict],
    log: Callable[[str], None] = print,
) -> list[dict]:
    """Keep stocks whose sector index has non-negative 5-day performance (with tolerance).

    Uses 5-trading-day change instead of single-day to avoid noise rejection.
    Tolerance: SECTOR_5D_TOLERANCE (-0.5%) allows minor dips.
    """
    if not stocks:
        return []

    kite = _get_kite(access_token)

    # Collect unique sector indices needed
    needed_indices = set()
    for s in stocks:
        si = s.get("sector_index")
        if si:
            needed_indices.add(si)

    # Resolve sector index instrument tokens
    sector_token_map = _get_sector_index_tokens()

    # Fetch historical data for each sector index
    sector_change: dict[str, float] = {}
    for idx_symbol in needed_indices:
        token = sector_token_map.get(idx_symbol)
        if not token:
            log(f"No instrument token for {idx_symbol}, skipping")
            sector_change[idx_symbol] = 0.0
            continue
        try:
            to_date = datetime.now()
            from_date = to_date - timedelta(days=SECTOR_HISTORY_CALENDAR_DAYS)
            history = kite.historical_data(
                token,
                from_date.strftime("%Y-%m-%d"),
                to_date.strftime("%Y-%m-%d"),
                "day",
            )
            if history and len(history) >= 5:
                # 5-trading-day performance
                recent_close = history[-1]["close"]
                five_days_ago_close = history[-5]["close"]
                if five_days_ago_close > 0:
                    change_pct = ((recent_close - five_days_ago_close) / five_days_ago_close) * 100
                else:
                    change_pct = 0.0
                sector_change[idx_symbol] = round(change_pct, 2)
            elif history and len(history) >= 2:
                # Fallback to available range
                change_pct = ((history[-1]["close"] - history[0]["close"]) / history[0]["close"]) * 100
                sector_change[idx_symbol] = round(change_pct, 2)
            else:
                sector_change[idx_symbol] = 0.0
            time.sleep(0.35)
        except Exception as e:
            log(f"Sector history failed for {idx_symbol}: {e}")
            sector_change[idx_symbol] = 0.0

    log(f"Sector 5-day performance: {json.dumps(sector_change, indent=2)}")

    # Filter with tolerance
    passed = []
    for stock in stocks:
        si = stock.get("sector_index", "")
        change = sector_change.get(si, 0.0)
        stock["sector_5d_change"] = change
        if change >= SECTOR_5D_TOLERANCE:
            passed.append(stock)

    log(f"Sector health filter: {len(passed)} / {len(stocks)} passed (tolerance: {SECTOR_5D_TOLERANCE}%)")
    return passed


# ---------------------------------------------------------------------------
# Composite Scoring
# ---------------------------------------------------------------------------

def compute_composite_scores(stocks: list[dict], log: Callable[[str], None] = print) -> list[dict]:
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
            # Lower RSI = better pullback entry (0-10)
            tech_score += max(0, min(10, int((50 - rsi) / 3)))
        else:
            tech_score += 5  # momentum gets flat 5

        adx = stock.get("adx", 0)
        tech_score += min(10, int(adx / 4))  # ADX strength (0-10)

        price = stock.get("current_price", 0)
        ema200 = stock.get("ema_200", price)
        if ema200 > 0:
            ema_dist_pct = ((price - ema200) / ema200) * 100
            tech_score += min(5, int(ema_dist_pct / 5))  # EMA distance (0-5)

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
    log(f"Composite scores computed. Top: {stocks[0]['symbol']}={stocks[0]['composite_score']}, "
        f"Bottom: {stocks[-1]['symbol']}={stocks[-1]['composite_score']}" if stocks else "No stocks to score")
    return stocks


# ---------------------------------------------------------------------------
# News Scraping (Google News RSS)
# ---------------------------------------------------------------------------

def _fetch_news_headlines(symbol: str, days: int = NEWS_LOOKBACK_DAYS) -> list[dict]:
    """Fetch recent news headlines from Google News RSS for a stock.

    Returns list of dicts with 'title', 'published' keys (max 10).
    """
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
        print(f"[DecisionSupport] News fetch failed for {symbol}: {e}")
        return []


# ---------------------------------------------------------------------------
# AI-Powered Stock Ranking (replaces generate_why_selected)
# ---------------------------------------------------------------------------

def ai_rank_stocks(
    stocks: list[dict],
    market_regime: dict,
    log: Callable[[str], None] = print,
    llm_provider: Optional[str] = None,
) -> list[dict]:
    """AI-powered stock ranking with news sentiment analysis.

    For each stock:
    1. Fetches recent news headlines
    2. Sends all data (technical, fundamental, news, market context) to LLM
    3. Gets conviction score (1-10), reason, and news sentiment

    Claude path: extended thinking, plus primary_risk and trade_type per stock.
    """
    from agents.config import get_llm
    from constants import CLAUDE_CONVICTION_THINKING_BUDGET

    if llm_provider == "claude":
        llm = get_llm(
            temperature=0.1,
            provider="claude",
            extended_thinking=True,
            thinking_budget=CLAUDE_CONVICTION_THINKING_BUDGET,
        )
    else:
        llm = get_llm(temperature=0.3)

    # Step 1: Fetch news for all stocks (threaded)
    news_map: dict[str, list[dict]] = {}
    def fetch_news(symbol: str):
        return symbol, _fetch_news_headlines(symbol)

    log(f"Fetching news for {len(stocks)} stocks...")
    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = [executor.submit(fetch_news, s["symbol"]) for s in stocks]
        for future in as_completed(futures):
            sym, headlines = future.result()
            news_map[sym] = headlines
    log(f"News fetched. Building AI ranking prompt...")

    # Step 2: Build prompt with all context
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

    if llm_provider == "claude":
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
    else:
        prompt = (
            "You are a senior trading analyst evaluating Indian NSE stocks that passed a 4-stage screening pipeline.\n\n"
            f"Market Context:\n"
            f"- India VIX: {vix} (Regime: {regime})\n"
            f"- {len(stocks)} stocks survived from the pipeline\n\n"
            f"Stock Data:\n"
            + "\n".join(stock_data_lines)
            + "\n\nFor EACH stock, provide:\n"
            "1. conviction_score: integer 1-10 (10 = highest conviction trade)\n"
            "2. reason: one sentence (max 25 words) explaining the trading opportunity\n"
            "3. news_sentiment: integer 1-5 (1 = very negative, 3 = neutral, 5 = very positive)\n"
            "4. news_flag: \"warning\" if negative news could impact the stock, otherwise \"clear\"\n\n"
            "Consider: technical setup quality, fundamental strength, news sentiment, sector momentum, "
            "and current market regime when scoring conviction.\n\n"
            "Return ONLY a JSON array of objects with keys: symbol, conviction_score, reason, news_sentiment, news_flag.\n"
            "No markdown, no explanation outside the JSON."
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

        for s in stocks:
            rank_data = ranking_map.get(s["symbol"], {})
            s["ai_conviction"] = max(1, min(10, rank_data.get("conviction_score", 5)))
            s["why_selected"] = rank_data.get("reason",
                f"Passed all filters with RSI {s.get('rsi', 'N/A')}")
            s["news_sentiment"] = max(1, min(5, rank_data.get("news_sentiment", 3)))
            s["news_flag"] = rank_data.get("news_flag", "clear")
            s["news_headlines"] = [h["title"] for h in news_map.get(s["symbol"], [])[:3]]
            # Claude-only fields
            if llm_provider == "claude":
                s["primary_risk"] = rank_data.get("primary_risk")
                s["trade_type"] = rank_data.get("trade_type")

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
) -> list[dict]:
    """Agent 6 — Portfolio Ranker.

    Takes the final shortlist (after all 5 pipeline stages) and produces a
    transparent multi-factor final ranking:

    Weights:
      35% AI conviction  (normalized 1-10 → 0-100)
      25% composite score (already 0-100)
      15% relative strength vs Nifty (min-max over batch)
      15% fundamental quality (ROE + D/E + profit growth → 0-100)
      10% sector momentum (min-max over batch)

    Then calls the LLM to write a 1-sentence rank_reason per stock.
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
    rs_raw         = [
        (s.get("stock_3m_return") or 0) - (s.get("nifty_3m_return") or 0)
        for s in stocks
    ]
    fund_raw       = [_fundamental_score(s) for s in stocks]
    sector_raw     = [s.get("sector_5d_change") or 0 for s in stocks]

    conv_norm   = _minmax(conviction_raw)
    comp_norm   = _minmax(composite_raw)
    rs_norm     = _minmax(rs_raw)
    fund_norm   = _minmax(fund_raw)
    sector_norm = _minmax(sector_raw)

    for i, s in enumerate(stocks):
        s["rank_factors"] = {
            "ai_conviction_norm":    round(conv_norm[i], 1),
            "composite_score_norm":  round(comp_norm[i], 1),
            "relative_strength_norm": round(rs_norm[i], 1),
            "fundamental_norm":      round(fund_norm[i], 1),
            "sector_momentum_norm":  round(sector_norm[i], 1),
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

    # LLM rank explanations
    try:
        from agents.config import get_llm
        llm = get_llm(temperature=0.2, provider=llm_provider)

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

        if llm_provider == "claude":
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
        else:
            prompt = (
                "You are a quantitative analyst. These stocks are ranked by a multi-factor formula "
                "(AI conviction 35%, composite score 25%, relative strength vs Nifty 15%, "
                "fundamentals 15%, sector momentum 10%). "
                "For each stock write exactly 1 concise sentence (max 25 words) explaining "
                "why it achieved its specific rank, citing the 2-3 strongest differentiating signals.\n\n"
                + "\n".join(summary_lines)
                + "\n\nReturn ONLY a JSON array: "
                '[{"symbol":"X","rank_reason":"..."},...] — no markdown, no extra text.'
            )

        response = llm.invoke(prompt)
        raw = response.content.strip() if hasattr(response, "content") else str(response)
        # Strip markdown fences if present
        if "```" in raw:
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
            raw = raw.strip()
        m = _re.search(r"\[.*\]", raw, _re.DOTALL)
        if m:
            reasons = json.loads(m.group())
            reason_map = {r["symbol"]: r for r in reasons}
            for s in stocks:
                entry = reason_map.get(s["symbol"], {})
                s["rank_reason"] = entry.get("rank_reason", "")
                if llm_provider == "claude":
                    s["portfolio_note"] = entry.get("portfolio_note", "diversified")
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
