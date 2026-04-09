"""Shared data infrastructure — per-pipeline session cache.

Provides:
    PipelineSession             — request-scoped cache container (use this for new code)
    clear_session_cache()       — reset module-level globals (backward-compat)
    resolve_instrument_tokens() — fetch NSE tokens from Kite API (cached)
    fetch_historical()          — fetch + cache OHLCV data from Kite API
    fetch_nifty()               — fetch Nifty 50 history (token 256265, cached)
    load_sector_indices()       — load sector_indices.json
    get_sector_index_tokens()   — build sector symbol → token map
    load_universe()             — load a universe CSV (nifty100/500/midcap/smallcap)
    build_symbol_sector_map()   — build symbol → {sector, sector_index} map

Backward compatibility
----------------------
All public functions accept an optional ``session: Optional[PipelineSession] = None``
parameter.  When ``session`` is provided the function reads/writes the session's
attributes, giving full isolation per pipeline run.  When ``session`` is ``None``
(the default) the legacy module-level globals are used, so existing callers that
do not pass a session continue to work unchanged.

New pipeline entry points should:
    session = PipelineSession()
    ... pass session=session through every tool call ...
"""

import json
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable, Optional

import pandas as pd

from config import DATA_DIR


# ---------------------------------------------------------------------------
# Request-scoped cache container
# ---------------------------------------------------------------------------

class PipelineSession:
    """Isolates all per-pipeline data so concurrent runs don't share state.

    Create one at the pipeline entry point and thread it through every tool
    function via the ``session=`` keyword argument.

    Attributes mirror the legacy module-level globals so the refactor is
    purely additive — old callers that don't pass a session use the globals.
    """

    __slots__ = (
        "session_cache",
        "nifty_cache",
        "sector_index_cache",
        "instrument_map",
        "universe_cache",
        "symbol_sector_map",
    )

    def __init__(self) -> None:
        self.session_cache: dict[int, pd.DataFrame] = {}
        self.nifty_cache: Optional[pd.DataFrame] = None
        self.sector_index_cache: dict[str, pd.DataFrame] = {}
        self.instrument_map: Optional[dict[str, int]] = None
        self.universe_cache: dict[str, pd.DataFrame] = {}
        self.symbol_sector_map: dict[str, dict] = {}

    def clear(self) -> None:
        """Reset all caches in this session."""
        self.session_cache = {}
        self.nifty_cache = None
        self.sector_index_cache = {}
        self.instrument_map = None
        self.universe_cache = {}
        self.symbol_sector_map = {}


# ---------------------------------------------------------------------------
# Module-level session caches — kept for backward compatibility
# ---------------------------------------------------------------------------
_session_cache: dict[int, pd.DataFrame] = {}          # instrument_token → OHLCV DF
_nifty_cache: Optional[pd.DataFrame] = None
_sector_index_cache: dict[str, pd.DataFrame] = {}     # sector_index symbol → OHLCV DF
_instrument_map: Optional[dict[str, int]] = None       # tradingsymbol → instrument_token
_universe_cache: dict[str, pd.DataFrame] = {}         # universe name → DataFrame
_symbol_sector_map: dict[str, dict] = {}              # symbol → {sector, sector_index}

_DATA_DIR = DATA_DIR

_UNIVERSE_FILES = {
    "nifty100": "nifty100.csv",
    "nifty500": "nifty500.csv",
    "nifty_midcap150": "nifty_midcap150.csv",
    "nifty_smallcap250": "nifty_smallcap250.csv",
}


def clear_session_cache(session: Optional["PipelineSession"] = None) -> None:
    """Reset all caches.  If a session is provided, clears the session; otherwise
    resets the legacy module-level globals (backward-compat)."""
    if session is not None:
        session.clear()
        return
    global _session_cache, _nifty_cache, _sector_index_cache
    global _instrument_map, _universe_cache, _symbol_sector_map
    _session_cache = {}
    _nifty_cache = None
    _sector_index_cache = {}
    _instrument_map = None
    _universe_cache = {}
    _symbol_sector_map = {}


# ---------------------------------------------------------------------------
# Instrument token resolution
# ---------------------------------------------------------------------------

def resolve_instrument_tokens(
    kite,
    log: Callable = print,
    session: Optional["PipelineSession"] = None,
) -> dict[str, int]:
    """Fetch NSE instrument tokens from Kite API. Cached for the session."""
    global _instrument_map
    cached = session.instrument_map if session is not None else _instrument_map
    if cached is not None:
        return cached
    log("Fetching NSE instrument list from Kite API...")
    instruments = kite.instruments("NSE")
    result: dict[str, int] = {}
    for inst in instruments:
        sym = inst.get("tradingsymbol")
        token = inst.get("instrument_token")
        if sym and token:
            result[sym] = token
    log(f"Loaded {len(result)} NSE instrument tokens")
    if session is not None:
        session.instrument_map = result
    else:
        _instrument_map = result
    return result


# ---------------------------------------------------------------------------
# Historical data fetch + cache
# ---------------------------------------------------------------------------

def fetch_historical(
    kite,
    instrument_token: int,
    symbol: str,
    days: int = 400,
    session: Optional["PipelineSession"] = None,
) -> Optional[pd.DataFrame]:
    """Fetch daily OHLCV data from Kite.

    Cache hierarchy:
        L1 — PipelineSession (per-request, in-memory)
        L2 — Redis (shared across requests, TTL 24h)
        L3 — Kite API (live fetch)
    """
    sc = session.session_cache if session is not None else _session_cache
    if instrument_token in sc:
        return sc[instrument_token]

    # L2: Redis
    from services.cache_service import ohlcv_cache_key, get_dataframe, set_dataframe
    redis_key = ohlcv_cache_key(instrument_token)
    cached_df = get_dataframe(redis_key)
    if cached_df is not None:
        if session is not None:
            session.session_cache[instrument_token] = cached_df
        else:
            _session_cache[instrument_token] = cached_df
        return cached_df

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
        if session is not None:
            session.session_cache[instrument_token] = df
        else:
            _session_cache[instrument_token] = df
        set_dataframe(redis_key, df)
        return df
    except Exception as e:
        err_msg = str(e)
        if "permission" in err_msg.lower() or "Insufficient" in err_msg:
            print(
                f"[DataInfra] Permission error for {symbol} — "
                f"check API key has historical data add-on: {err_msg}"
            )
        else:
            print(f"[DataInfra] Historical fetch failed for {symbol}: {err_msg}")
        return None


def fetch_nifty(
    kite,
    days: int = 400,
    session: Optional["PipelineSession"] = None,
) -> Optional[pd.DataFrame]:
    """Fetch Nifty 50 historical data (token 256265). Cached for the session."""
    global _nifty_cache
    cached = session.nifty_cache if session is not None else _nifty_cache
    if cached is not None:
        return cached
    result = fetch_historical(kite, 256265, "NIFTY50", days=days, session=session)
    if session is not None:
        session.nifty_cache = result
    else:
        _nifty_cache = result
    return result


# ---------------------------------------------------------------------------
# Sector index helpers
# ---------------------------------------------------------------------------

def load_sector_indices() -> dict:
    """Load sector → index mapping from sector_indices.json."""
    json_path = _DATA_DIR / "sector_indices.json"
    with open(json_path) as f:
        return json.load(f)


def get_sector_index_tokens(instrument_map: dict[str, int]) -> dict[str, int]:
    """Build sector index symbol → instrument_token map.

    Sector index symbols in sector_indices.json look like "NSE:NIFTY AUTO".
    NSE instruments list has tradingsymbol "NIFTY AUTO" (without "NSE:").
    """
    sector_indices = load_sector_indices()
    result: dict[str, int] = {}
    for _, idx_symbol in sector_indices.items():
        ts = idx_symbol.replace("NSE:", "")
        token = instrument_map.get(ts)
        if token:
            result[idx_symbol] = token
    return result


# ---------------------------------------------------------------------------
# Universe CSV loading
# ---------------------------------------------------------------------------

def load_universe(name: str = "nifty500", session: Optional["PipelineSession"] = None) -> pd.DataFrame:
    """Load a stock universe CSV (cached at module level).

    Args:
        name: one of 'nifty100', 'nifty500', 'nifty_midcap150', 'nifty_smallcap250'.

    Raises:
        ValueError: if the universe name is not recognized.
        FileNotFoundError: if the CSV file does not exist.
    """
    uc = session.universe_cache if session is not None else _universe_cache
    if name in uc:
        return uc[name]
    filename = _UNIVERSE_FILES.get(name)
    if filename is None:
        raise ValueError(
            f"Unknown universe '{name}'. "
            f"Valid options: {', '.join(_UNIVERSE_FILES.keys())}"
        )
    csv_path = _DATA_DIR / filename
    if not csv_path.exists():
        raise FileNotFoundError(
            f"Universe file not found: {csv_path}."
        )
    df = pd.read_csv(csv_path)
    uc[name] = df
    return df


# ---------------------------------------------------------------------------
# Symbol → sector map (built from all universe CSVs)
# ---------------------------------------------------------------------------

def build_symbol_sector_map(
    log: Callable = print,
    session: Optional["PipelineSession"] = None,
) -> dict[str, dict]:
    """Build a combined symbol → {sector, sector_index} map from all universe CSVs.

    Cached after first build. Call clear_session_cache() to rebuild.
    """
    global _symbol_sector_map
    ssm = session.symbol_sector_map if session is not None else _symbol_sector_map
    if ssm:
        return ssm

    result: dict[str, dict] = {}
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
                if sym and sym not in result:
                    result[sym] = {
                        "sector": row.get("sector", "Unknown"),
                        "sector_index": row.get("sector_index"),
                    }
        except Exception as e:
            log(f"Warning: could not load {fname}: {e}")

    log(f"Loaded sector map with {len(result)} symbols")
    if session is not None:
        session.symbol_sector_map = result
    else:
        _symbol_sector_map = result
    return result
