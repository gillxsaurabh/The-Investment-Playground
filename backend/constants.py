"""Re-export of all analysis constants from YAML config.

Values live in backend/config/analysis_params.yaml — edit them there.
All existing `from constants import X` imports continue to work unchanged.
"""

from services.params import params as _p

# --- Technical indicator periods ---
ADX_PERIOD    = _p.get("ADX_PERIOD")
EMA_SHORT     = _p.get("EMA_SHORT")
EMA_LONG      = _p.get("EMA_LONG")
EMA_TREND     = _p.get("EMA_TREND")
RSI_PERIOD    = _p.get("RSI_PERIOD")
ATR_PERIOD    = _p.get("ATR_PERIOD")

# --- Decision support thresholds ---
RSI_BUY_LIMIT = _p.get("RSI_BUY_LIMIT")
MIN_TURNOVER  = _p.get("MIN_TURNOVER")

# --- Decision support pipeline (Phase 1) ---
ADX_PIPELINE_MIN             = _p.get("ADX_PIPELINE_MIN")
STRICT_ROE_MIN               = _p.get("STRICT_ROE_MIN")
STRICT_DE_MAX                = _p.get("STRICT_DE_MAX")
SECTOR_5D_TOLERANCE          = _p.get("SECTOR_5D_TOLERANCE")
SECTOR_HISTORY_CALENDAR_DAYS = _p.get("SECTOR_HISTORY_CALENDAR_DAYS")

# --- Decision support pipeline (Phase 2) ---
MIN_VOLUME_RATIO    = _p.get("MIN_VOLUME_RATIO")
YOY_QUARTERS_NEEDED = _p.get("YOY_QUARTERS_NEEDED")

# --- Decision support pipeline (Phase 3) ---
VIX_HIGH_THRESHOLD  = _p.get("VIX_HIGH_THRESHOLD")
VIX_RSI_TIGHTENING  = _p.get("VIX_RSI_TIGHTENING")

# Graduated VIX response tiers
VIX_TIER1_THRESHOLD  = _p.get("VIX_TIER1_THRESHOLD")
VIX_TIER2_THRESHOLD  = _p.get("VIX_TIER2_THRESHOLD")
VIX_TIER3_THRESHOLD  = _p.get("VIX_TIER3_THRESHOLD")
VIX_TIER1_RSI_TIGHTEN = _p.get("VIX_TIER1_RSI_TIGHTEN")
VIX_TIER2_RSI_TIGHTEN = _p.get("VIX_TIER2_RSI_TIGHTEN")
NEWS_LOOKBACK_DAYS      = _p.get("NEWS_LOOKBACK_DAYS")
NEWS_NEGATIVE_THRESHOLD = _p.get("NEWS_NEGATIVE_THRESHOLD")

# --- Analysis score weights ---
WEIGHT_RECENCY       = _p.get("WEIGHT_RECENCY")
WEIGHT_TREND         = _p.get("WEIGHT_TREND")
WEIGHT_FUNDAMENTALS  = _p.get("WEIGHT_FUNDAMENTALS")
WEIGHT_AI_SENTIMENT  = _p.get("WEIGHT_AI_SENTIMENT")

# --- Fundamental thresholds ---
ROE_EXCELLENT = _p.get("ROE_EXCELLENT")
ROE_GOOD      = _p.get("ROE_GOOD")
ROE_POOR      = _p.get("ROE_POOR")
DE_LOW        = _p.get("DE_LOW")
DE_MODERATE   = _p.get("DE_MODERATE")
DE_HIGH       = _p.get("DE_HIGH")

# --- Simulator ---
SPREAD_FACTOR          = _p.get("SPREAD_FACTOR")
MAX_HISTORY_SECONDS    = _p.get("MAX_HISTORY_SECONDS")
DEFAULT_TRAIL_MULTIPLIER = _p.get("DEFAULT_TRAIL_MULTIPLIER")
STALL_EXIT_DAYS        = _p.get("STALL_EXIT_DAYS")
DEFAULT_INITIAL_CAPITAL = _p.get("DEFAULT_INITIAL_CAPITAL")

# --- Rate limiting ---
KITE_API_DELAY    = _p.get("KITE_API_DELAY")
SCREENER_API_DELAY = _p.get("SCREENER_API_DELAY")

# --- Cache ---
NIFTY_CACHE_DURATION  = _p.get("NIFTY_CACHE_DURATION")
HISTORICAL_DATA_DAYS  = _p.get("HISTORICAL_DATA_DAYS")
ATR_HISTORICAL_DAYS   = _p.get("ATR_HISTORICAL_DAYS")

# --- Relative strength thresholds ---
RS_STRONG_OUTPERFORM = _p.get("RS_STRONG_OUTPERFORM")
RS_UNDERPERFORM      = _p.get("RS_UNDERPERFORM")

# --- ADX thresholds ---
ADX_STRONG_TREND   = _p.get("ADX_STRONG_TREND")
ADX_MODERATE_TREND = _p.get("ADX_MODERATE_TREND")

# --- Historical data column mapping (Kite -> standard) ---
KITE_COLUMN_MAP = _p.section("kite_column_map")

# --- LLM provider constants (non-YAML — string literals are fine) ---
LLM_PROVIDER_CLAUDE = "claude"
LLM_PROVIDER_OPENAI = "openai"

# --- Claude model & extended thinking budgets ---
CLAUDE_MODEL_DEFAULT              = _p.get("CLAUDE_MODEL_DEFAULT")
CLAUDE_SYNTHESIS_THINKING_BUDGET  = _p.get("CLAUDE_SYNTHESIS_THINKING_BUDGET")
CLAUDE_CONVICTION_THINKING_BUDGET = _p.get("CLAUDE_CONVICTION_THINKING_BUDGET")

# --- Sell analysis thresholds ---
SELL_RSI_OVERBOUGHT           = _p.get("SELL_RSI_OVERBOUGHT")
SELL_RSI_MOMENTUM_FAILED      = _p.get("SELL_RSI_MOMENTUM_FAILED")
SELL_ADX_WEAK                 = _p.get("SELL_ADX_WEAK")
SELL_RS_NIFTY_GAP             = _p.get("SELL_RS_NIFTY_GAP")
SELL_RS_SECTOR_GAP            = _p.get("SELL_RS_SECTOR_GAP")
SELL_PROFIT_DECLINE_QUARTERS  = _p.get("SELL_PROFIT_DECLINE_QUARTERS")
SELL_ROE_WEAK                 = _p.get("SELL_ROE_WEAK")
SELL_ROE_MODERATE             = _p.get("SELL_ROE_MODERATE")
SELL_DE_HIGH                  = _p.get("SELL_DE_HIGH")
SELL_PNL_LOSS_THRESHOLD       = _p.get("SELL_PNL_LOSS_THRESHOLD")
SELL_PNL_DEEP_LOSS_THRESHOLD  = _p.get("SELL_PNL_DEEP_LOSS_THRESHOLD")

# --- Position sizing ---
RISK_PER_TRADE_PCT = _p.get("RISK_PER_TRADE_PCT")
MAX_POSITION_PCT   = _p.get("MAX_POSITION_PCT")

# --- Automation sell integration ---
AUTO_SELL_URGENCY_THRESHOLD = _p.get("AUTO_SELL_URGENCY_THRESHOLD")

# --- Drawdown protection ---
MAX_DRAWDOWN_PCT = _p.get("MAX_DRAWDOWN_PCT")

# --- Trailing stop profit tightening ---
TRAIL_TIGHTEN_PROFIT_ATR = _p.get("TRAIL_TIGHTEN_PROFIT_ATR")
TRAIL_TIGHTEN_FACTOR     = _p.get("TRAIL_TIGHTEN_FACTOR")

# --- Sell urgency score bands ---
SELL_URGENCY_STRONG = _p.get("SELL_URGENCY_STRONG")
SELL_URGENCY_SELL   = _p.get("SELL_URGENCY_SELL")
SELL_URGENCY_WATCH  = _p.get("SELL_URGENCY_WATCH")

# --- Unified Stock Audit: health score weights (sum = 10.0) ---
AUDIT_WEIGHT_TECHNICAL   = _p.get("AUDIT_WEIGHT_TECHNICAL")
AUDIT_WEIGHT_FUNDAMENTAL = _p.get("AUDIT_WEIGHT_FUNDAMENTAL")
AUDIT_WEIGHT_RS          = _p.get("AUDIT_WEIGHT_RS")
AUDIT_WEIGHT_NEWS        = _p.get("AUDIT_WEIGHT_NEWS")
AUDIT_WEIGHT_POSITION    = _p.get("AUDIT_WEIGHT_POSITION")

# --- Audit health label thresholds ---
AUDIT_HEALTHY = _p.get("AUDIT_HEALTHY")
AUDIT_STABLE  = _p.get("AUDIT_STABLE")
AUDIT_WATCH   = _p.get("AUDIT_WATCH")

# --- Claude thinking budget for audit AI enrichment ---
AUDIT_AI_THINKING_BUDGET = _p.get("AUDIT_AI_THINKING_BUDGET")

# --- Live trading risk controls ---
LIVE_MAX_POSITION_SIZE   = _p.get("LIVE_MAX_POSITION_SIZE")
LIVE_MAX_DAILY_LOSS      = _p.get("LIVE_MAX_DAILY_LOSS")
LIVE_MAX_OPEN_POSITIONS  = _p.get("LIVE_MAX_OPEN_POSITIONS")
LIVE_MAX_ORDER_VALUE     = _p.get("LIVE_MAX_ORDER_VALUE")

# --- Sell pipeline data settings ---
SELL_HISTORICAL_DAYS    = _p.get("SELL_HISTORICAL_DAYS")
SELL_MOMENTUM_LOOKBACK  = _p.get("SELL_MOMENTUM_LOOKBACK")
SELL_VOLUME_DRY_RATIO   = _p.get("SELL_VOLUME_DRY_RATIO")
