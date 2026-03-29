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

# --- Decision support pipeline (Phase 1) ---
ADX_PIPELINE_MIN = 20             # Minimum ADX for trend confirmation in Filter 2
STRICT_ROE_MIN = 15.0             # Minimum ROE for "strict" fundamental check (Gear 1)
STRICT_DE_MAX = 1.0               # Maximum D/E for "strict" fundamental check (Gear 1)
SECTOR_5D_TOLERANCE = -0.5        # Allow sector 5-day change down to -0.5%
SECTOR_HISTORY_CALENDAR_DAYS = 15 # Fetch 15 calendar days to get 5+ trading days

# --- Decision support pipeline (Phase 2) ---
MIN_VOLUME_RATIO = 0.7            # 5-day/20-day avg volume ratio minimum (distribution filter)
YOY_QUARTERS_NEEDED = 5           # Need at least 5 quarters for YoY comparison

# --- Decision support pipeline (Phase 3) ---
VIX_HIGH_THRESHOLD = 20           # VIX above this = elevated fear
VIX_RSI_TIGHTENING = 5            # Legacy: kept for reference; graduated tiers used instead

# Graduated VIX response tiers
VIX_TIER1_THRESHOLD = 20   # VIX 20-25 → mild caution  → tighten RSI by 3
VIX_TIER2_THRESHOLD = 25   # VIX 25-30 → high fear     → tighten RSI by 7, limit to Gear 1-3
VIX_TIER3_THRESHOLD = 30   # VIX >30   → extreme fear  → pause automation entirely
VIX_TIER1_RSI_TIGHTEN = 3
VIX_TIER2_RSI_TIGHTEN = 7
NEWS_LOOKBACK_DAYS = 7            # Days of news to fetch
NEWS_NEGATIVE_THRESHOLD = 2       # AI sentiment score below this = warning

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
STALL_EXIT_DAYS = 12   # Trading days (not calendar days) without a new high before stall exit
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

# --- LLM provider constants ---
LLM_PROVIDER_GEMINI = "gemini"
LLM_PROVIDER_CLAUDE = "claude"
LLM_PROVIDER_OPENAI = "openai"

# --- Claude model & extended thinking budgets ---
CLAUDE_MODEL_DEFAULT              = "claude-sonnet-4-6"
CLAUDE_SYNTHESIS_THINKING_BUDGET  = 5000   # synthesizer: reconcile 3 conflicting signals
CLAUDE_CONVICTION_THINKING_BUDGET = 10000  # conviction engine: rank 5-20 stocks simultaneously

# --- Sell analysis thresholds ---
SELL_RSI_OVERBOUGHT = 70           # RSI above this → overbought signal
SELL_RSI_MOMENTUM_FAILED = 40      # RSI below this after being above 50 → momentum reversal
SELL_ADX_WEAK = 20                 # ADX below this + falling = trend breakdown
SELL_RS_NIFTY_GAP = -10.0         # 3M return vs Nifty below this → relative weakness
SELL_RS_SECTOR_GAP = -10.0        # 3M return vs sector below this → sector laggard
SELL_PROFIT_DECLINE_QUARTERS = 2   # consecutive declining quarters triggers flag
SELL_ROE_WEAK = 10.0              # ROE below this → fundamental red flag
SELL_ROE_MODERATE = 15.0          # ROE below this → minor flag
SELL_DE_HIGH = 3.0                # D/E above this → high debt flag
SELL_PNL_LOSS_THRESHOLD = -15.0   # unrealized P&L% below this → position health flag
SELL_PNL_DEEP_LOSS_THRESHOLD = -25.0  # deep loss threshold

# --- Position sizing ---
RISK_PER_TRADE_PCT = 0.01      # Risk 1% of capital per trade
MAX_POSITION_PCT = 0.25        # Single position cannot exceed 25% of capital

# --- Automation sell integration ---
AUTO_SELL_URGENCY_THRESHOLD = 70   # Sell urgency score >= this triggers auto-close in automation

# --- Drawdown protection ---
MAX_DRAWDOWN_PCT = 0.20    # Pause automation if equity is down >20% from initial capital

# --- Trailing stop profit tightening ---
TRAIL_TIGHTEN_PROFIT_ATR = 2.0   # Once unrealized profit >= N × ATR, tighten the trail
TRAIL_TIGHTEN_FACTOR = 0.75      # Multiply the trail_multiplier by this factor when tightening

# --- Sell urgency score bands ---
SELL_URGENCY_STRONG = 70   # Score >= this → STRONG SELL
SELL_URGENCY_SELL = 40     # Score >= this → SELL
SELL_URGENCY_WATCH = 20    # Score >= this → WATCH
                           # Score < 20 → HOLD

# --- Unified Stock Audit: health score weights (sum = 10.0) ---
AUDIT_WEIGHT_TECHNICAL    = 3.0   # RSI, ADX, EMA alignment, volume
AUDIT_WEIGHT_FUNDAMENTAL  = 2.5   # ROE, D/E, profit trend
AUDIT_WEIGHT_RS           = 2.0   # 3M relative strength vs Nifty + sector
AUDIT_WEIGHT_NEWS         = 1.5   # AI-analyzed news sentiment
AUDIT_WEIGHT_POSITION     = 1.0   # Current unrealized P&L health

# --- Audit health label thresholds ---
AUDIT_HEALTHY  = 7.5   # Score >= this → HEALTHY
AUDIT_STABLE   = 5.0   # Score >= this → STABLE
AUDIT_WATCH    = 3.0   # Score >= this → WATCH
               # Score < 3.0 → CRITICAL

# --- Claude thinking budget for audit AI enrichment ---
AUDIT_AI_THINKING_BUDGET = 10000

# --- Live trading risk controls ---
LIVE_MAX_POSITION_SIZE = 0.20      # Single position cannot exceed 20% of equity
LIVE_MAX_DAILY_LOSS = 0.05         # Halt if daily realized loss > 5% of equity
LIVE_MAX_OPEN_POSITIONS = 10       # Maximum concurrent live positions
LIVE_MAX_ORDER_VALUE = 500_000     # Single order cap: ₹5 lakhs

# --- Sell pipeline data settings ---
SELL_HISTORICAL_DAYS = 400         # Days of OHLCV to fetch for sell analysis (enough for EMA-200)
SELL_MOMENTUM_LOOKBACK = 10        # Days to look back for RSI momentum failure detection
SELL_VOLUME_DRY_RATIO = 0.60       # 5d/20d volume ratio below this = volume drying up (distribution signal)
