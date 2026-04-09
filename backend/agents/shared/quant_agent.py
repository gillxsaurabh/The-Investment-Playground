"""Shared Quant Agent — unified technical indicator computation and batch enrichment.

Provides:
    compute_indicators(df)              — compute RSI, ADX, ATR, EMAs, volume stats
    compute_relative_strength(...)      — compute 3M stock vs Nifty return
    enrich_with_technicals(items, ...)  — batch technical enrichment (mode="enrich"|"filter")
"""

import threading
import time
from typing import Callable, Optional

import pandas as pd

from agents.shared.data_infra import fetch_historical, fetch_nifty, PipelineSession
from constants import SELL_MOMENTUM_LOOKBACK
from services.technical import calculate_adx, calculate_rsi as _canonical_rsi


# ---------------------------------------------------------------------------
# Single-stock indicator computation
# ---------------------------------------------------------------------------

def compute_indicators(df: Optional[pd.DataFrame]) -> dict:
    """Compute all technical indicators for a single stock DataFrame.

    Returns a dict with keys:
        rsi, adx, atr, ema_20, ema_50, ema_200,
        avg_volume_20d, avg_volume_5d, volume_ratio,
        rsi_series, current_price

    All values may be None if df is None or too short.
    """
    empty = {
        "rsi": None, "adx": None, "atr": None,
        "ema_20": None, "ema_50": None, "ema_200": None,
        "avg_volume_20d": None, "avg_volume_5d": None, "volume_ratio": None,
        "rsi_series": None, "current_price": None,
    }
    if df is None or len(df) < 30:
        return empty

    try:
        current_price = round(float(df["Close"].iloc[-1]), 2)

        def _ema(span: int) -> Optional[float]:
            val = df["Close"].ewm(span=span, adjust=False).mean().iloc[-1]
            return round(float(val), 2) if not pd.isna(val) else None

        ema_20 = _ema(20)
        ema_50 = _ema(50)
        ema_200 = _ema(200)

        rsi_series = _canonical_rsi(df["Close"], period=14)
        rsi = round(float(rsi_series.iloc[-1]), 2) if not rsi_series.empty else None

        adx = calculate_adx(df)
        adx = round(float(adx), 2) if adx is not None else None

        # ATR
        try:
            high = df["High"]
            low = df["Low"]
            prev_close = df["Close"].shift(1)
            tr = pd.concat([
                high - low,
                (high - prev_close).abs(),
                (low - prev_close).abs(),
            ], axis=1).max(axis=1)
            atr_val = tr.rolling(window=14).mean().iloc[-1]
            atr = round(float(atr_val), 2) if not pd.isna(atr_val) else None
        except Exception:
            atr = None

        avg_volume_20d = round(float(df["Volume"].tail(20).mean()), 0)
        avg_volume_5d = round(float(df["Volume"].tail(5).mean()), 0)
        volume_ratio = (
            round(float(avg_volume_5d / avg_volume_20d), 2)
            if avg_volume_20d > 0 else 1.0
        )

        return {
            "rsi": rsi,
            "adx": adx,
            "atr": atr,
            "ema_20": ema_20,
            "ema_50": ema_50,
            "ema_200": ema_200,
            "avg_volume_20d": avg_volume_20d,
            "avg_volume_5d": avg_volume_5d,
            "volume_ratio": volume_ratio,
            "rsi_series": rsi_series,
            "current_price": current_price,
        }
    except Exception as e:
        print(f"[QuantAgent] compute_indicators failed: {e}")
        return empty


def compute_relative_strength(
    stock_df: Optional[pd.DataFrame],
    nifty_df: Optional[pd.DataFrame],
    lookback: int = 63,
) -> dict:
    """Compute 3-month (63 trading day) relative strength vs Nifty.

    Returns dict with keys:
        stock_3m_return   (float or None)
        nifty_3m_return   (float or None)
    """
    stock_3m = None
    nifty_3m = None

    if stock_df is not None and len(stock_df) >= lookback:
        current = float(stock_df["Close"].iloc[-1])
        past = float(stock_df["Close"].iloc[-lookback])
        stock_3m = round(((current / past) - 1) * 100, 2)

    if nifty_df is not None and len(nifty_df) >= lookback:
        current = float(nifty_df["Close"].iloc[-1])
        past = float(nifty_df["Close"].iloc[-lookback])
        nifty_3m = round(((current / past) - 1) * 100, 2)

    return {"stock_3m_return": stock_3m, "nifty_3m_return": nifty_3m}


# ---------------------------------------------------------------------------
# Batch enrichment
# ---------------------------------------------------------------------------

def enrich_with_technicals(
    items: list[dict],
    kite,
    nifty_df: Optional[pd.DataFrame] = None,
    log: Callable = print,
    mode: str = "enrich",
    historical_days: int = 400,
    session: Optional[PipelineSession] = None,
) -> list[dict]:
    """Batch technical enrichment for a list of stock/holding dicts.

    Each item must have 'symbol' and 'instrument_token' keys.

    Adds keys to each item:
        current_price, rsi, adx, atr, ema_20, ema_50, ema_200,
        avg_volume_20d, avg_volume_5d, volume_ratio,
        stock_3m_return, nifty_3m_return, _rsi_history

    Args:
        mode: "enrich" — all items pass through (failed items get None values).
              "filter" — items with no historical data are dropped.
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed

    # Fetch Nifty benchmark if not supplied
    if nifty_df is None:
        nifty_df = fetch_nifty(kite, days=historical_days, session=session)

    nifty_3m_return = 0.0
    if nifty_df is not None and len(nifty_df) >= 63:
        nifty_3m_return = round(
            ((float(nifty_df["Close"].iloc[-1]) / float(nifty_df["Close"].iloc[-63])) - 1) * 100, 2
        )
    log(f"Nifty 50 3M return: {nifty_3m_return:.2f}%")

    rate_lock = threading.Lock()
    enriched_count = [0]
    failed_count = [0]

    def enrich_one(item: dict) -> Optional[dict]:
        symbol = item["symbol"]
        token = item["instrument_token"]

        with rate_lock:
            time.sleep(0.35)

        df = fetch_historical(kite, token, symbol, days=historical_days, session=session)

        if df is None or len(df) < 30:
            with rate_lock:
                failed_count[0] += 1
            log(f"  {symbol}: data unavailable — {'dropping' if mode == 'filter' else 'keeping with null indicators'}")
            if mode == "filter":
                return None
            # enrich mode: keep item with None indicators
            item.update({
                "current_price": item.get("last_price"),
                "rsi": None, "adx": None, "atr": None,
                "ema_20": None, "ema_50": None, "ema_200": None,
                "avg_volume_20d": None, "avg_volume_5d": None, "volume_ratio": None,
                "stock_3m_return": None,
                "nifty_3m_return": round(nifty_3m_return, 2),
                "_rsi_history": [],
            })
            return item

        indicators = compute_indicators(df)
        rs = compute_relative_strength(df, nifty_df)

        # Build RSI history for momentum-failure detection (sell pipeline uses this)
        rsi_history = []
        if indicators["rsi_series"] is not None:
            rsi_history = [
                round(float(v), 2)
                for v in indicators["rsi_series"].dropna().tail(SELL_MOMENTUM_LOOKBACK + 2).tolist()
            ]

        with rate_lock:
            enriched_count[0] += 1

        ema_200_str = "below" if indicators["ema_200"] and indicators["current_price"] < indicators["ema_200"] else "above"
        log(
            f"  {symbol}: price={indicators['current_price']}, RSI={indicators['rsi']}, "
            f"ADX={indicators['adx']}, EMA200={ema_200_str}"
        )

        item.update({
            "current_price": indicators["current_price"],
            "rsi": indicators["rsi"],
            "adx": indicators["adx"],
            "atr": indicators["atr"],
            "ema_20": indicators["ema_20"],
            "ema_50": indicators["ema_50"],
            "ema_200": indicators["ema_200"],
            "avg_volume_20d": indicators["avg_volume_20d"],
            "avg_volume_5d": indicators["avg_volume_5d"],
            "volume_ratio": indicators["volume_ratio"],
            "stock_3m_return": rs["stock_3m_return"],
            "nifty_3m_return": rs["nifty_3m_return"] if rs["nifty_3m_return"] is not None else round(nifty_3m_return, 2),
            "_rsi_history": rsi_history,
        })
        return item

    log(f"Fetching OHLCV and computing indicators for {len(items)} items...")
    results = []
    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = {executor.submit(enrich_one, item): item["symbol"] for item in items}
        for future in futures:
            result = future.result()
            if result is not None:
                results.append(result)

    log(
        f"Technical scan complete: {enriched_count[0]} enriched, "
        f"{failed_count[0]} {'dropped' if mode == 'filter' else 'data unavailable'}"
    )
    return results
