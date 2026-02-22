"""SSE streaming generator for the Decision Support pipeline.

Orchestrates the 4 tools sequentially, yielding SSE events at each step
so the frontend can display a live "thought chain" and progress stepper.
"""

import json
from datetime import datetime

from agents.decision_support.strategy_config import STRATEGY_GEARS, DEFAULT_GEAR
from agents.decision_support.tools import (
    clear_session_cache,
    filter_market_universe,
    analyze_technicals,
    check_fundamentals,
    check_sector_health,
    generate_why_selected,
)


def _sse(event: str, data: dict) -> str:
    """Format a Server-Sent Event string."""
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


def run_decision_support_stream(access_token: str, config: dict | None = None):
    """Generator yielding SSE events as the 4-2-1-1 pipeline runs.

    Args:
        access_token: Kite Connect access token.
        config: Optional strategy config overrides. Supports 'gear' (int 1-5)
            which resolves to a preset profile, plus individual overrides:
            rsi_buy_limit, min_turnover, ema_period, universe, fundamental_check.

    Events emitted:
        step_start    — a pipeline stage is beginning
        step_log      — intermediate progress message
        step_complete — a stage finished (includes stocks_remaining count)
        final_result  — the selected stocks with all details
        error         — a stage failed fatally
    """
    if config is None:
        config = {}

    # Resolve gear preset — individual params in config override gear defaults
    gear = config.get("gear", DEFAULT_GEAR)
    gear_profile = STRATEGY_GEARS.get(gear, STRATEGY_GEARS[DEFAULT_GEAR])
    resolved = {**gear_profile, **{k: v for k, v in config.items() if k != "gear"}}

    clear_session_cache()
    started_at = datetime.now().isoformat()
    yield _sse("step_start", {
        "step": "pipeline",
        "description": "Starting Decision Support Agent...",
        "started_at": started_at,
    })

    # Collect log messages via callback
    logs: list[str] = []

    def make_logger(step_name: str):
        def log_fn(msg: str):
            logs.append(msg)
            print(f"[DecisionSupport] [{step_name}] {msg}")
        return log_fn

    # ── Step 1: Universe Filter ──────────────────────────────────────────
    universe_key = resolved.get("universe", "nifty500")
    universe_label = universe_key.replace("_", " ").title()
    yield _sse("step_start", {
        "step": "universe_filter",
        "description": f"Screening {universe_label} universe (volume, EMA, relative strength)...",
    })

    universe_stocks = []
    total_scanned = 0
    try:
        log_fn = make_logger("universe_filter")

        def universe_log(msg):
            log_fn(msg)
            # We can't yield from inside a callback, so we collect logs
            # and they'll be sent as step_log events below

        universe_stocks = filter_market_universe(
            access_token,
            log=universe_log,
            min_turnover=resolved.get("min_turnover", 50_000_000),
            ema_period=resolved.get("ema_period", 200),
            universe=universe_key,
        )
    except Exception as e:
        yield _sse("error", {"step": "universe_filter", "message": str(e)})
        return

    # Extract total scanned from logs (the loader logs the count)
    # We parse it from the first log message which contains the stock count
    for msg in logs:
        if "list:" in msg and "stocks" in msg:
            try:
                total_scanned = int(msg.split("list:")[1].split("stocks")[0].strip())
            except (ValueError, IndexError):
                pass
            break
    if total_scanned == 0:
        total_scanned = len(universe_stocks) or 500  # fallback

    # Send collected logs
    for msg in logs:
        yield _sse("step_log", {"step": "universe_filter", "message": msg})
    logs.clear()

    yield _sse("step_complete", {
        "step": "universe_filter",
        "stocks_remaining": len(universe_stocks),
        "initial_count": total_scanned,
    })

    if not universe_stocks:
        yield _sse("final_result", {
            "stocks": [],
            "total_scanned": total_scanned,
            "total_selected": 0,
            "message": "No stocks passed the universe filter. Market conditions may be weak.",
            "completed_at": datetime.now().isoformat(),
        })
        return

    # ── Step 2: Technical Setup ──────────────────────────────────────────
    yield _sse("step_start", {
        "step": "technical_setup",
        "description": f"Analyzing technical setups for {len(universe_stocks)} stocks (20-EMA, RSI)...",
    })

    technical_stocks = []
    try:
        log_fn = make_logger("technical_setup")
        technical_stocks = analyze_technicals(
            universe_stocks,
            log=log_fn,
            rsi_buy_limit=resolved.get("rsi_buy_limit", 30),
        )
    except Exception as e:
        yield _sse("error", {"step": "technical_setup", "message": str(e)})
        return

    for msg in logs:
        yield _sse("step_log", {"step": "technical_setup", "message": msg})
    logs.clear()

    yield _sse("step_complete", {
        "step": "technical_setup",
        "stocks_remaining": len(technical_stocks),
        "previous_count": len(universe_stocks),
    })

    if not technical_stocks:
        yield _sse("final_result", {
            "stocks": [],
            "total_scanned": total_scanned,
            "total_selected": 0,
            "message": "No stocks have valid RSI entry setups right now.",
            "completed_at": datetime.now().isoformat(),
        })
        return

    # ── Step 3: Fundamental Check ────────────────────────────────────────
    yield _sse("step_start", {
        "step": "fundamentals",
        "description": f"Checking quarterly profit growth for {len(technical_stocks)} stocks...",
    })

    fundamental_stocks = []
    try:
        log_fn = make_logger("fundamentals")
        fundamental_stocks = check_fundamentals(
            technical_stocks,
            log=log_fn,
            fundamental_check=resolved.get("fundamental_check", "standard"),
        )
    except Exception as e:
        yield _sse("error", {"step": "fundamentals", "message": str(e)})
        return

    for msg in logs:
        yield _sse("step_log", {"step": "fundamentals", "message": msg})
    logs.clear()

    yield _sse("step_complete", {
        "step": "fundamentals",
        "stocks_remaining": len(fundamental_stocks),
        "previous_count": len(technical_stocks),
    })

    if not fundamental_stocks:
        yield _sse("final_result", {
            "stocks": [],
            "total_scanned": total_scanned,
            "total_selected": 0,
            "message": "No stocks show improving quarterly profits among technical picks.",
            "completed_at": datetime.now().isoformat(),
        })
        return

    # ── Step 4: Sector Health ────────────────────────────────────────────
    yield _sse("step_start", {
        "step": "sector_health",
        "description": f"Checking sector health for {len(fundamental_stocks)} stocks...",
    })

    final_stocks = []
    try:
        log_fn = make_logger("sector_health")
        final_stocks = check_sector_health(access_token, fundamental_stocks, log=log_fn)
    except Exception as e:
        yield _sse("error", {"step": "sector_health", "message": str(e)})
        return

    for msg in logs:
        yield _sse("step_log", {"step": "sector_health", "message": msg})
    logs.clear()

    yield _sse("step_complete", {
        "step": "sector_health",
        "stocks_remaining": len(final_stocks),
        "previous_count": len(fundamental_stocks),
    })

    # ── Generate "Why Selected" reasons ──────────────────────────────────
    if final_stocks:
        yield _sse("step_log", {
            "step": "sector_health",
            "message": "Generating AI-powered selection reasons...",
        })
        try:
            final_stocks = generate_why_selected(final_stocks, log=print)
        except Exception:
            pass  # Fallback reasons already set in generate_why_selected

    # ── Final Result ─────────────────────────────────────────────────────
    # Clean up stock dicts for frontend consumption
    result_stocks = []
    for s in final_stocks:
        result_stocks.append({
            "symbol": s.get("symbol"),
            "instrument_token": s.get("instrument_token"),
            "current_price": s.get("current_price"),
            "rsi": s.get("rsi"),
            "rsi_trigger": s.get("rsi_trigger"),
            "sector": s.get("sector"),
            "sector_daily_change": s.get("sector_daily_change"),
            "why_selected": s.get("why_selected", ""),
            "ema_20": s.get("ema_20"),
            "ema_200": s.get("ema_200"),
            "stock_3m_return": s.get("stock_3m_return"),
            "nifty_3m_return": s.get("nifty_3m_return"),
            "avg_volume_20d": s.get("avg_volume_20d"),
        })

    yield _sse("final_result", {
        "stocks": result_stocks,
        "total_scanned": total_scanned,
        "total_selected": len(result_stocks),
        "gear": gear,
        "gear_label": gear_profile.get("label", "Balanced"),
        "atr_stop_loss_multiplier": resolved.get("atr_stop_loss_multiplier", 1.5),
        "message": (
            f"Pipeline complete: {len(result_stocks)} stocks selected from {total_scanned}."
            if result_stocks
            else "No stocks currently meet all criteria. The market may lack strong setups."
        ),
        "started_at": started_at,
        "completed_at": datetime.now().isoformat(),
    })
