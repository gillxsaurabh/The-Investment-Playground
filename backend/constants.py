"""All magic numbers and domain constants for CogniCap.

Consolidates hardcoded values previously scattered across stock_analyzer.py,
stock_health_service.py, agents/decision_support/strategy_config.py, app.py,
and simulator.py.
"""

# --- Technical indicator periods ---
ADX_PERIOD = 14
EMA_SHORT = 20
EMA_LONG = 50
EMA_TREND = 200
RSI_PERIOD = 14
ATR_PERIOD = 14

# --- Decision support thresholds ---
RSI_BUY_LIMIT = 30
MIN_TURNOVER = 50_000_000  # 5 Crores

# --- Analysis score weights ---
WEIGHT_RECENCY = 0.25
WEIGHT_TREND = 0.25
WEIGHT_FUNDAMENTALS = 0.30
WEIGHT_AI_SENTIMENT = 0.20

# --- Fundamental thresholds ---
ROE_EXCELLENT = 15
ROE_GOOD = 10
ROE_POOR = 5
DE_LOW = 1.0
DE_MODERATE = 2.0
DE_HIGH = 3.0

# --- Simulator ---
SPREAD_FACTOR = 0.0005       # 0.05% impact cost
MAX_HISTORY_SECONDS = 600    # 10 minutes of 1-second price snapshots
DEFAULT_TRAIL_MULTIPLIER = 1.5
STALL_EXIT_DAYS = 7
DEFAULT_INITIAL_CAPITAL = 100_000.0

# --- Rate limiting ---
KITE_API_DELAY = 0.2          # seconds between Kite API calls
SCREENER_API_DELAY = 1.0      # seconds between screener.in requests

# --- Nifty cache ---
NIFTY_CACHE_DURATION = 3600   # 1 hour in seconds
HISTORICAL_DATA_DAYS = 180    # 6 months
ATR_HISTORICAL_DAYS = 30

# --- Relative strength thresholds ---
RS_STRONG_OUTPERFORM = 5      # percentage points above Nifty
RS_UNDERPERFORM = -5

# --- ADX thresholds ---
ADX_STRONG_TREND = 25
ADX_MODERATE_TREND = 20

# --- Historical data column mapping (Kite -> standard) ---
KITE_COLUMN_MAP = {
    'open': 'Open',
    'high': 'High',
    'low': 'Low',
    'close': 'Close',
    'volume': 'Volume',
}
