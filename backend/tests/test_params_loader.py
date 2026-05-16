"""Sanity tests for the YAML params loader.

Verifies every expected constant is present, types are correct, and prompt
templates have their required {var} placeholders.
"""

import string
import pytest


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def p():
    from services.params import params
    return params


@pytest.fixture(scope="module")
def pr():
    from services.params import prompts
    return pr


# ---------------------------------------------------------------------------
# Params: key presence and types
# ---------------------------------------------------------------------------

_EXPECTED_INT_KEYS = [
    "ADX_PERIOD", "EMA_SHORT", "EMA_LONG", "EMA_TREND", "RSI_PERIOD", "ATR_PERIOD",
    "SECTOR_HISTORY_CALENDAR_DAYS", "YOY_QUARTERS_NEEDED",
    "VIX_TIER1_THRESHOLD", "VIX_TIER2_THRESHOLD", "VIX_TIER3_THRESHOLD",
    "VIX_TIER1_RSI_TIGHTEN", "VIX_TIER2_RSI_TIGHTEN",
    "NEWS_LOOKBACK_DAYS", "NEWS_NEGATIVE_THRESHOLD",
    "ROE_EXCELLENT", "ROE_GOOD", "ROE_POOR",
    "SELL_PROFIT_DECLINE_QUARTERS",
    "SELL_URGENCY_STRONG", "SELL_URGENCY_SELL", "SELL_URGENCY_WATCH",
    "CLAUDE_SYNTHESIS_THINKING_BUDGET", "CLAUDE_CONVICTION_THINKING_BUDGET",
    "AUDIT_AI_THINKING_BUDGET",
    "SELL_HISTORICAL_DAYS", "SELL_MOMENTUM_LOOKBACK",
]

_EXPECTED_FLOAT_KEYS = [
    "STRICT_ROE_MIN", "STRICT_DE_MAX", "SECTOR_5D_TOLERANCE", "MIN_VOLUME_RATIO",
    "WEIGHT_RECENCY", "WEIGHT_TREND", "WEIGHT_FUNDAMENTALS", "WEIGHT_AI_SENTIMENT",
    "RANK_WEIGHT_AI_CONVICTION", "RANK_WEIGHT_COMPOSITE", "RANK_WEIGHT_RS",
    "RANK_WEIGHT_FUNDAMENTAL", "RANK_WEIGHT_SECTOR",
    "RS_STRONG_OUTPERFORM", "RS_UNDERPERFORM",
    "DE_LOW", "DE_MODERATE", "DE_HIGH",
    "SELL_RSI_OVERBOUGHT", "SELL_RSI_MOMENTUM_FAILED", "SELL_ADX_WEAK",
    "SELL_RS_NIFTY_GAP", "SELL_RS_SECTOR_GAP",
    "SELL_ROE_WEAK", "SELL_ROE_MODERATE", "SELL_DE_HIGH",
    "SELL_PNL_LOSS_THRESHOLD", "SELL_PNL_DEEP_LOSS_THRESHOLD",
    "SELL_VOLUME_DRY_RATIO",
    "AUDIT_WEIGHT_TECHNICAL", "AUDIT_WEIGHT_FUNDAMENTAL", "AUDIT_WEIGHT_RS",
    "AUDIT_WEIGHT_NEWS", "AUDIT_WEIGHT_POSITION",
    "AUDIT_HEALTHY", "AUDIT_STABLE", "AUDIT_WATCH",
    "ADX_STRONG_TREND", "ADX_MODERATE_TREND",
]


@pytest.mark.parametrize("key", _EXPECTED_INT_KEYS)
def test_int_params_present(p, key):
    val = p.get(key)
    assert isinstance(val, int), f"{key} should be int, got {type(val).__name__}"


@pytest.mark.parametrize("key", _EXPECTED_FLOAT_KEYS)
def test_float_params_present(p, key):
    val = p.get(key)
    assert isinstance(val, (int, float)), f"{key} should be numeric, got {type(val).__name__}"


def test_missing_key_raises(p):
    with pytest.raises(KeyError, match="not found"):
        p.get("NONEXISTENT_KEY_XYZ")


def test_missing_key_with_default(p):
    assert p.get("NONEXISTENT_KEY_XYZ", 42) == 42


def test_composite_weights_sum(p):
    total = sum([
        p.get("WEIGHT_RECENCY"),
        p.get("WEIGHT_TREND"),
        p.get("WEIGHT_FUNDAMENTALS"),
        p.get("WEIGHT_AI_SENTIMENT"),
    ])
    assert abs(total - 1.0) < 0.001, f"Composite weights sum to {total}, expected 1.0"


def test_ranking_weights_sum(p):
    total = sum([
        p.get("RANK_WEIGHT_AI_CONVICTION"),
        p.get("RANK_WEIGHT_COMPOSITE"),
        p.get("RANK_WEIGHT_RS"),
        p.get("RANK_WEIGHT_FUNDAMENTAL"),
        p.get("RANK_WEIGHT_SECTOR"),
    ])
    assert abs(total - 1.0) < 0.001, f"Ranking weights sum to {total}, expected 1.0"


def test_audit_weights_sum(p):
    total = sum([
        p.get("AUDIT_WEIGHT_TECHNICAL"),
        p.get("AUDIT_WEIGHT_FUNDAMENTAL"),
        p.get("AUDIT_WEIGHT_RS"),
        p.get("AUDIT_WEIGHT_NEWS"),
        p.get("AUDIT_WEIGHT_POSITION"),
    ])
    assert abs(total - 10.0) < 0.001, f"Audit weights sum to {total}, expected 10.0"


def test_sell_urgency_bands_ordering(p):
    assert p.get("SELL_URGENCY_STRONG") > p.get("SELL_URGENCY_SELL") > p.get("SELL_URGENCY_WATCH")


def test_gear_profiles(p):
    for gear_num in range(1, 6):
        gear = p.gear(gear_num)
        assert "label" in gear
        assert "universe" in gear
        assert "rsi_buy_limit" in gear
        assert isinstance(gear["atr_stop_loss_multiplier"], (int, float))


def test_sell_urgency_points_section(p):
    pts = p.sell_urgency_points()
    assert "technical.price_below_ema200" in pts
    assert "fundamental.roe_weak" in pts
    assert "position_health.deep_loss" in pts
    assert all(isinstance(v, (int, float)) for v in pts.values())


# ---------------------------------------------------------------------------
# Prompts: presence and placeholder validation
# ---------------------------------------------------------------------------

_PROMPT_REQUIRED_VARS = {
    "ai_conviction_engine": {"vix", "regime", "vix_note", "len_stocks", "stock_data_lines"},
    "portfolio_ranker": {"sector_distribution", "summary_lines"},
    "sell_signal_engine": {"vix", "regime", "len_holdings", "holding_lines"},
    "quantitative_analyst": {"symbol", "recency_score", "recency_detail", "trend_score",
                             "trend_strength", "trend_direction", "stats_score"},
    "fundamentals_analyst": {"symbol", "roe_str", "de_str", "sg_str", "score"},
    "news_sentinel": {"symbol"},
    "synthesizer": {"symbol", "conflict_instruction", "stats_score", "stats_explanation",
                    "health_score", "health_explanation", "news_score", "news_explanation",
                    "risk_flags_str"},
    "supervisor_router": {"agent_descriptions", "agent_names"},
    "worker_template": {"description"},
    "general_chat": set(),
    "portfolio_chat": set(),
}


def _extract_template_vars(template: str) -> set:
    """Return set of {var} placeholder names from a format-string template."""
    formatter = string.Formatter()
    return {fname for _, fname, _, _ in formatter.parse(template) if fname is not None}


@pytest.mark.parametrize("name,required_vars", _PROMPT_REQUIRED_VARS.items())
def test_prompt_has_required_vars(name, required_vars):
    from services.params import prompts
    template = prompts.get(name)
    found_vars = _extract_template_vars(template)
    missing = required_vars - found_vars
    assert not missing, (
        f"Prompt '{name}' is missing placeholders: {missing}. "
        f"Found: {found_vars}"
    )


def test_all_expected_prompts_loadable():
    from services.params import prompts
    for name in _PROMPT_REQUIRED_VARS:
        template = prompts.get(name)
        assert isinstance(template, str) and len(template) > 10, (
            f"Prompt '{name}' is empty or missing"
        )


def test_prompt_missing_key_raises():
    from services.params import prompts
    with pytest.raises(KeyError, match="not found"):
        prompts.get("nonexistent_prompt_xyz")


# ---------------------------------------------------------------------------
# Constants.py backward compatibility
# ---------------------------------------------------------------------------

def test_constants_backward_compat():
    """Verify constants.py still exports all expected names."""
    import constants
    expected = [
        "ADX_PERIOD", "EMA_SHORT", "EMA_LONG", "EMA_TREND", "RSI_PERIOD", "ATR_PERIOD",
        "SELL_RSI_OVERBOUGHT", "SELL_URGENCY_STRONG", "SELL_URGENCY_SELL",
        "AUDIT_WEIGHT_TECHNICAL", "AUDIT_HEALTHY", "CLAUDE_MODEL_DEFAULT",
        "VIX_TIER1_THRESHOLD", "KITE_COLUMN_MAP",
    ]
    for name in expected:
        assert hasattr(constants, name), f"constants.py missing: {name}"
        assert getattr(constants, name) is not None


def test_strategy_config_backward_compat():
    """Verify strategy_config.py still exports STRATEGY_GEARS and DEFAULT_GEAR."""
    from agents.decision_support.strategy_config import STRATEGY_GEARS, DEFAULT_GEAR
    assert isinstance(STRATEGY_GEARS, dict)
    assert set(STRATEGY_GEARS.keys()) == {1, 2, 3, 4, 5}
    assert STRATEGY_GEARS[3]["label"] == "Balanced"
    assert DEFAULT_GEAR == 3
