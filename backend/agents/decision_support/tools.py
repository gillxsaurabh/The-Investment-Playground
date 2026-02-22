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

# ---------------------------------------------------------------------------
# Module-level caches (cleared at the start of each pipeline run)
# ---------------------------------------------------------------------------
_session_cache: dict[int, pd.DataFrame] = {}   # instrument_token → historical DF
_nifty_cache: Optional[pd.DataFrame] = None

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
    global _session_cache, _nifty_cache, _instrument_map, _universe_cache
    _session_cache = {}
    _nifty_cache = None
    _instrument_map = None
    _universe_cache = {}


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
    """Calculate RSI using standard Wilder's smoothing."""
    delta = df["Close"].diff()
    gain = delta.where(delta > 0, 0.0)
    loss = (-delta.where(delta < 0, 0.0))
    avg_gain = gain.rolling(window=period, min_periods=period).mean()
    avg_loss = loss.rolling(window=period, min_periods=period).mean()
    # Wilder smoothing for subsequent values
    for i in range(period, len(avg_gain)):
        avg_gain.iloc[i] = (avg_gain.iloc[i - 1] * (period - 1) + gain.iloc[i]) / period
        avg_loss.iloc[i] = (avg_loss.iloc[i - 1] * (period - 1) + loss.iloc[i]) / period
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    return rsi


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
    """Filter stock universe: avg turnover > min_turnover, price > EMA, relative strength > Nifty.

    Volume is calculated as the 20-day average from historical candles (not today's
    quote volume, which is 0 during pre-market).

    Returns list of stock dicts with keys:
        symbol, instrument_token, sector, sector_index, current_price,
        avg_volume_20d, stock_3m_return, nifty_3m_return
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

    # --- Step 3: Threaded historical fetch for ALL stocks -----------------
    # We fetch historical data for every stock because we need it for:
    #   - 20-day average volume (can't rely on quote volume pre-market)
    #   - 200-day EMA
    #   - 3-month relative strength
    # The data is cached in _session_cache so Tool 2 doesn't re-fetch.

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
    # Per-filter rejection counters for diagnostics
    counters = {
        "fetch_failed": 0,
        "too_few_candles": 0,
        "volume_rejected": 0,
        "ema_rejected": 0,
        "ema_nan": 0,
        "rs_rejected": 0,
        "passed": 0,
    }

    def fetch_and_filter(stock: dict) -> Optional[dict]:
        with rate_lock:
            request_count[0] += 1
            # Kite rate limit: ~3 requests/sec; with 5 threads, pause every request
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

        # --- Turnover filter: 20-day avg (price × volume) ------------------
        avg_volume_20d = df["Volume"].tail(20).mean()
        avg_price_20d = df["Close"].tail(20).mean()
        avg_turnover_20d = avg_volume_20d * avg_price_20d
        if avg_turnover_20d < min_turnover:
            with rate_lock:
                counters["volume_rejected"] += 1
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

        # --- 3-month relative strength vs Nifty --------------------------
        if len(df) >= 63:
            stock_3m_return = ((current_price / df["Close"].iloc[-63]) - 1) * 100
        else:
            stock_3m_return = 0.0

        if stock_3m_return <= nifty_3m_return:
            with rate_lock:
                counters["rs_rejected"] += 1
            return None

        with rate_lock:
            counters["passed"] += 1

        stock["current_price"] = round(current_price, 2)
        stock["avg_volume_20d"] = round(avg_volume_20d, 0)
        stock["avg_turnover_20d"] = round(avg_turnover_20d, 0)
        stock["ema_200"] = round(ema_val, 2)
        stock["stock_3m_return"] = round(stock_3m_return, 2)
        stock["nifty_3m_return"] = round(nifty_3m_return, 2)
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
    log(f"  Total stocks:       {len(all_stocks)}")
    log(f"  Fetch failed:       {counters['fetch_failed']}")
    log(f"  Too few candles:    {counters['too_few_candles']}")
    log(f"  Turnover too low:   {counters['volume_rejected']}")
    log(f"  EMA NaN:            {counters['ema_nan']}")
    log(f"  Price <= 200-EMA:   {counters['ema_rejected']}")
    log(f"  Rel. strength fail: {counters['rs_rejected']}")
    log(f"  PASSED:             {counters['passed']}")

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
    """Filter by 20-EMA momentum and RSI entry triggers.

    Keep if: Price > 20-EMA AND (RSI < rsi_buy_limit OR RSI crossed above 50 in last 3 days).
    Uses cached historical data from Tool 1 (no new API calls).
    """
    passed = []
    for stock in stocks:
        token = stock["instrument_token"]
        df = _session_cache.get(token)
        if df is None or len(df) < 20:
            continue

        current_price = df["Close"].iloc[-1]
        ema_20 = _calculate_ema(df["Close"], 20).iloc[-1]

        if current_price <= ema_20:
            continue

        rsi_series = _calculate_rsi(df, 14)
        if rsi_series.empty or rsi_series.isna().all():
            continue
        current_rsi = rsi_series.iloc[-1]

        # Entry trigger: RSI < rsi_buy_limit (pullback) OR RSI crossed above 50 recently
        pullback = current_rsi < rsi_buy_limit
        momentum = False
        if len(rsi_series) >= 4:
            for i in range(-3, 0):
                if rsi_series.iloc[i - 1] < 50 <= rsi_series.iloc[i]:
                    momentum = True
                    break

        if not pullback and not momentum:
            continue

        stock["ema_20"] = round(ema_20, 2)
        stock["rsi"] = round(current_rsi, 2)
        stock["rsi_trigger"] = "pullback" if pullback else "momentum"
        passed.append(stock)

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


def check_fundamentals(
    stocks: list[dict],
    log: Callable[[str], None] = print,
    fundamental_check: str = "standard",
) -> list[dict]:
    """Filter stocks based on fundamental health.

    Args:
        fundamental_check: one of "strict", "standard", "loose", "none".
            - strict:   quarterly profit must be growing (same as standard for now)
            - standard: current quarter profit > previous quarter profit
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
    else:
        # "standard" and "strict" both use profit growth
        def check_one(stock: dict) -> Optional[dict]:
            growing = _get_quarterly_profit_growth(stock["symbol"])
            if growing is True:
                stock["quarterly_profit_growth"] = True
                return stock
            return None

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
    """Keep stocks whose sector index had a non-negative previous close change.

    Uses historical candles instead of live quotes so it works pre-market.
    Change % = (yesterday_close - day_before_close) / day_before_close * 100
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

    # Fetch last 5 days of historical data for each sector index
    sector_change: dict[str, float] = {}
    for idx_symbol in needed_indices:
        token = sector_token_map.get(idx_symbol)
        if not token:
            log(f"No instrument token for {idx_symbol}, skipping")
            sector_change[idx_symbol] = 0.0
            continue
        try:
            to_date = datetime.now()
            from_date = to_date - timedelta(days=10)  # 10 calendar days to ensure 2+ trading days
            history = kite.historical_data(
                token,
                from_date.strftime("%Y-%m-%d"),
                to_date.strftime("%Y-%m-%d"),
                "day",
            )
            if history and len(history) >= 2:
                yesterday_close = history[-1]["close"]
                day_before_close = history[-2]["close"]
                if day_before_close > 0:
                    change_pct = ((yesterday_close - day_before_close) / day_before_close) * 100
                else:
                    change_pct = 0.0
                sector_change[idx_symbol] = round(change_pct, 2)
            else:
                sector_change[idx_symbol] = 0.0
            time.sleep(0.35)
        except Exception as e:
            log(f"Sector history failed for {idx_symbol}: {e}")
            sector_change[idx_symbol] = 0.0

    log(f"Sector performance (prev close change): {json.dumps(sector_change, indent=2)}")

    # Filter
    passed = []
    for stock in stocks:
        si = stock.get("sector_index", "")
        change = sector_change.get(si, 0.0)
        stock["sector_daily_change"] = change
        if change >= 0:
            passed.append(stock)

    log(f"Sector health filter: {len(passed)} / {len(stocks)} passed")
    return passed


# ---------------------------------------------------------------------------
# Why-Selected reasoning (OpenAI)
# ---------------------------------------------------------------------------

def generate_why_selected(stocks: list[dict], log: Callable[[str], None] = print) -> list[dict]:
    """Use OpenAI to generate a one-line 'why_selected' reason for each stock."""
    try:
        from langchain_openai import ChatOpenAI
        openai_key = os.getenv("OPENAI_API_KEY")
        if not openai_key:
            for s in stocks:
                s["why_selected"] = (
                    f"Strong technicals (RSI: {s.get('rsi', 'N/A')}, "
                    f"above 20/200 EMA) + profit growth + positive sector"
                )
            return stocks

        llm = ChatOpenAI(model="gpt-4o-mini", api_key=openai_key, temperature=0.3)

        stock_summaries = []
        for s in stocks:
            stock_summaries.append(
                f"- {s['symbol']}: Price={s.get('current_price')}, RSI={s.get('rsi')}, "
                f"Trigger={s.get('rsi_trigger')}, Sector={s.get('sector')}, "
                f"3M Return={s.get('stock_3m_return')}%, "
                f"Sector Change={s.get('sector_daily_change')}%"
            )

        prompt = (
            "You are a trading analyst. For each stock below, write ONE short sentence "
            "(max 15 words) explaining why it was selected as a trading opportunity. "
            "Focus on the key technical/fundamental reason.\n\n"
            + "\n".join(stock_summaries)
            + "\n\nReturn a JSON array of objects with 'symbol' and 'reason' keys."
        )

        response = llm.invoke(prompt)
        content = response.content.strip()
        # Extract JSON from response
        if "```" in content:
            content = content.split("```")[1]
            if content.startswith("json"):
                content = content[4:]
            content = content.strip()
        reasons = json.loads(content)
        reason_map = {r["symbol"]: r["reason"] for r in reasons}

        for s in stocks:
            s["why_selected"] = reason_map.get(
                s["symbol"],
                f"Passed all 4 filters with RSI {s.get('rsi', 'N/A')}"
            )
    except Exception as e:
        log(f"OpenAI reasoning failed: {e}. Using fallback reasons.")
        for s in stocks:
            s["why_selected"] = (
                f"RSI {s.get('rsi', 'N/A')} {s.get('rsi_trigger', '')} setup, "
                f"profit growing, sector positive"
            )

    return stocks
