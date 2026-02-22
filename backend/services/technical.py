"""Pure technical indicator functions.

Consolidates ADX, EMA, RSI, ATR, True Range, and relative strength calculations
previously duplicated across stock_analyzer.py, stock_health_service.py,
agents/decision_support/tools.py, and app.py.

All functions are pure (no API calls, no side effects) and operate on pandas DataFrames.
"""

from typing import Optional, Tuple

import pandas as pd

from constants import (
    ADX_PERIOD,
    EMA_SHORT,
    EMA_LONG,
    ADX_STRONG_TREND,
    ADX_MODERATE_TREND,
)


def calculate_ema(series: pd.Series, span: int) -> pd.Series:
    """Calculate Exponential Moving Average."""
    return series.ewm(span=span, adjust=False).mean()


def calculate_true_range(df: pd.DataFrame) -> pd.Series:
    """Calculate True Range from OHLC data.

    Expects columns: 'High', 'Low', 'Close' (standard format).
    """
    high = df["High"]
    low = df["Low"]
    prev_close = df["Close"].shift(1)

    high_low = high - low
    high_close = (high - prev_close).abs()
    low_close = (low - prev_close).abs()

    return pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)


def calculate_atr(df: pd.DataFrame, period: int = 14) -> float:
    """Calculate Average True Range (simple moving average of True Range).

    Returns the last ATR value.
    """
    tr = calculate_true_range(df)
    return tr.tail(period).mean()


def calculate_adx(df: pd.DataFrame, period: int = ADX_PERIOD) -> Optional[float]:
    """Calculate Average Directional Index (ADX).

    Expects columns: 'High', 'Low', 'Close' (standard format).
    Returns the last ADX value or None on failure.
    """
    try:
        high = df["High"]
        low = df["Low"]
        close = df["Close"]

        # True Range
        high_low = high - low
        high_close = (high - close.shift()).abs()
        low_close = (low - close.shift()).abs()
        tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)

        # Directional Movement
        plus_dm = high.diff()
        minus_dm = -low.diff()
        plus_dm[plus_dm < 0] = 0
        minus_dm[minus_dm < 0] = 0

        # Smooth
        tr_smooth = tr.rolling(window=period).sum()
        plus_dm_smooth = plus_dm.rolling(window=period).sum()
        minus_dm_smooth = minus_dm.rolling(window=period).sum()

        # Directional Indicators
        plus_di = 100 * (plus_dm_smooth / tr_smooth)
        minus_di = 100 * (minus_dm_smooth / tr_smooth)

        # DX and ADX
        dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di)
        adx = dx.rolling(window=period).mean()

        return adx.iloc[-1] if not adx.empty else None
    except Exception:
        return None


def calculate_rsi(series: pd.Series, period: int = 14) -> pd.Series:
    """Calculate RSI using Wilder's smoothing method.

    Args:
        series: Price series (typically 'Close').
        period: RSI period (default 14).

    Returns:
        pd.Series of RSI values.
    """
    delta = series.diff()
    gain = delta.where(delta > 0, 0.0)
    loss = (-delta.where(delta < 0, 0.0))

    avg_gain = gain.rolling(window=period, min_periods=period).mean()
    avg_loss = loss.rolling(window=period, min_periods=period).mean()

    # Wilder smoothing for subsequent values
    for i in range(period, len(avg_gain)):
        avg_gain.iloc[i] = (avg_gain.iloc[i - 1] * (period - 1) + gain.iloc[i]) / period
        avg_loss.iloc[i] = (avg_loss.iloc[i - 1] * (period - 1) + loss.iloc[i]) / period

    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def calculate_relative_strength(
    stock_df: pd.DataFrame,
    benchmark_df: pd.DataFrame,
    days: int = 90,
) -> Tuple[float, float]:
    """Calculate relative strength of stock vs benchmark over a time period.

    Returns:
        (stock_return, benchmark_return) as percentages.
    """
    from datetime import datetime, timedelta

    cutoff = datetime.now() - timedelta(days=days)

    stock_recent = stock_df[stock_df.index >= cutoff]
    bench_recent = benchmark_df[benchmark_df.index >= cutoff]

    if stock_recent.empty or bench_recent.empty:
        return 0.0, 0.0

    stock_return = ((stock_recent["Close"].iloc[-1] / stock_recent["Close"].iloc[0]) - 1) * 100
    bench_return = ((bench_recent["Close"].iloc[-1] / bench_recent["Close"].iloc[0]) - 1) * 100

    return stock_return, bench_return


def calculate_technical_scores(
    stock_data: pd.DataFrame,
    nifty_data: Optional[pd.DataFrame],
) -> dict:
    """Calculate recency and trend scores for a stock.

    Returns dict with 'recency' and 'trend' sub-dicts, each containing 'score' and details.
    """
    # 1. Recency (Relative Strength vs Nifty)
    recency_score = 3
    recency_detail = "N/A"

    if nifty_data is not None and not nifty_data.empty:
        stock_return, nifty_return = calculate_relative_strength(stock_data, nifty_data, days=90)

        if stock_return > nifty_return + 5:
            recency_score = 5
            recency_detail = f"Strong outperformance: {stock_return:.1f}% vs Nifty {nifty_return:.1f}%"
        elif stock_return > nifty_return:
            recency_score = 4
            recency_detail = f"Outperforming: {stock_return:.1f}% vs Nifty {nifty_return:.1f}%"
        elif stock_return > nifty_return - 5:
            recency_score = 3
            recency_detail = f"In-line: {stock_return:.1f}% vs Nifty {nifty_return:.1f}%"
        else:
            recency_score = 2
            recency_detail = f"Underperforming: {stock_return:.1f}% vs Nifty {nifty_return:.1f}%"

    # 2. Trend (ADX + EMA crossover)
    trend_score = 3
    trend_strength = "N/A"
    trend_direction = "N/A"

    if len(stock_data) >= 50:
        current_adx = calculate_adx(stock_data)

        if current_adx is not None and pd.notna(current_adx):
            ema_20 = calculate_ema(stock_data["Close"], EMA_SHORT).iloc[-1]
            ema_50 = calculate_ema(stock_data["Close"], EMA_LONG).iloc[-1]
            current_price = stock_data["Close"].iloc[-1]

            if current_adx > ADX_STRONG_TREND:
                trend_strength = f"Strong (ADX: {current_adx:.1f})"
            elif current_adx > ADX_MODERATE_TREND:
                trend_strength = f"Moderate (ADX: {current_adx:.1f})"
            else:
                trend_strength = f"Weak (ADX: {current_adx:.1f})"

            if pd.notna(ema_20) and pd.notna(ema_50):
                if current_price > ema_20 > ema_50:
                    trend_direction = "Bullish"
                    trend_score = 5 if current_adx > ADX_STRONG_TREND else 4
                elif current_price < ema_20 < ema_50:
                    trend_direction = "Bearish"
                    trend_score = 1 if current_adx > ADX_STRONG_TREND else 2
                else:
                    trend_direction = "Mixed"
                    trend_score = 3

    return {
        "recency": {"score": recency_score, "detail": recency_detail},
        "trend": {"score": trend_score, "strength": trend_strength, "direction": trend_direction},
    }
