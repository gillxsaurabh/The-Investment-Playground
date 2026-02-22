"""Default strategy parameters for the Decision Support pipeline.

These values are used when the user doesn't override them via the UI.
"""

# RSI Configuration
DEFAULT_RSI_PERIOD = 14
DEFAULT_RSI_BUY_LIMIT = 30       # Buy signal if RSI < this value (pullback)

# EMA Configuration
DEFAULT_EMA_PERIOD = 200         # Trend filter: price must be above this EMA

# Volume / Turnover Configuration
DEFAULT_MIN_TURNOVER = 50_000_000  # 5 Crores (50M) minimum 20-day avg turnover

# ---------------------------------------------------------------------------
# Strategy Gears — preset profiles selected via the UI slider (1–5)
# ---------------------------------------------------------------------------

STRATEGY_GEARS = {
    1: {
        "label": "Fortress",
        "universe": "nifty100",
        "min_turnover": 500_000_000,      # 50 Cr (High Liquidity)
        "rsi_buy_limit": 30,              # Buy only Deep Dips
        "fundamental_check": "strict",
        "atr_stop_loss_multiplier": 2.0,
    },
    2: {
        "label": "Cautious",
        "universe": "nifty100",
        "min_turnover": 100_000_000,      # 10 Cr
        "rsi_buy_limit": 35,
        "fundamental_check": "standard",
        "atr_stop_loss_multiplier": 1.75,
    },
    3: {
        "label": "Balanced",
        "universe": "nifty500",
        "min_turnover": 50_000_000,       # 5 Cr
        "rsi_buy_limit": 40,
        "fundamental_check": "standard",
        "atr_stop_loss_multiplier": 1.5,
    },
    4: {
        "label": "Growth",
        "universe": "nifty_midcap150",
        "min_turnover": 20_000_000,       # 2 Cr (Allow smaller names)
        "rsi_buy_limit": 50,              # Buy shallow dips
        "fundamental_check": "loose",
        "atr_stop_loss_multiplier": 1.25,
    },
    5: {
        "label": "Turbo",
        "universe": "nifty_smallcap250",
        "min_turnover": 5_000_000,        # 50 Lakhs (Wild West)
        "rsi_buy_limit": 60,              # Buy Breakouts (Momentum)
        "fundamental_check": "none",
        "atr_stop_loss_multiplier": 1.0,
    },
}

DEFAULT_GEAR = 3
