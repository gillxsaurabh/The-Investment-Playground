"""Strategy gear profiles loaded from YAML config.

Values live in backend/config/analysis_params.yaml → strategy_gears.
All existing imports (`from agents.decision_support.strategy_config import STRATEGY_GEARS`) work unchanged.
"""

from services.params import params as _p

_gears_cfg = _p.all_gears()

# Build STRATEGY_GEARS with integer keys to match the original API
STRATEGY_GEARS: dict[int, dict] = {
    int(gear_num): dict(gear_data)
    for gear_num, gear_data in _gears_cfg.get("gears", {}).items()
}

DEFAULT_GEAR: int = int(_gears_cfg.get("default_gear", 3))

# Legacy exports used by tools.py — backed by YAML values
DEFAULT_RSI_PERIOD   = _p.get("RSI_PERIOD")
DEFAULT_RSI_BUY_LIMIT = _p.get("RSI_BUY_LIMIT")
DEFAULT_EMA_PERIOD   = _p.get("EMA_TREND")
DEFAULT_MIN_TURNOVER = _p.get("MIN_TURNOVER")
