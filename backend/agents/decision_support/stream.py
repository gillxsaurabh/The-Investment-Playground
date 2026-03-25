"""SSE streaming generator for the Decision Support pipeline.

Orchestrates the 4-2-1-1 tools sequentially + composite scoring + AI ranking,
yielding SSE events at each step so the frontend can display a live progress stepper.

Agents in the pipeline:
  1. Market Scanner       — screens universe by volume, 200-EMA and relative strength
  2. Quant Analyst        — validates RSI entry triggers with ADX trend confirmation
  3. Fundamentals Analyst — checks quarterly profit growth, ROE and D/E via Screener.in
  4. Sector Momentum      — confirms 5-day sector index tailwind
  5. AI Conviction Engine — composite scoring + LLM news sentiment ranking
  6. Portfolio Ranker     — multi-factor final ranking with LLM rank explanations
"""

import json
import time
from datetime import datetime

from agents.decision_support.strategy_config import STRATEGY_GEARS, DEFAULT_GEAR
from agents.decision_support.tools import (
    clear_session_cache,
    filter_market_universe,
    analyze_technicals,
    check_fundamentals,
    check_sector_health,
    compute_composite_scores,
    ai_rank_stocks,
    rank_final_shortlist,
)
from broker import get_broker
from constants import (
    VIX_TIER1_THRESHOLD, VIX_TIER2_THRESHOLD, VIX_TIER3_THRESHOLD,
    VIX_TIER1_RSI_TIGHTEN, VIX_TIER2_RSI_TIGHTEN,
)


def _sse(event: str, data: dict) -> str:
    """Format a Server-Sent Event string."""
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


def run_decision_support_stream(access_token: str, config: dict | None = None):
    """Generator yielding SSE events as the pipeline runs.

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

    # llm_provider flows automatically: frontend sends it in config dict
    llm_provider = resolved.get("llm_provider", None)

    clear_session_cache()
    started_at = datetime.now().isoformat()
    yield _sse("step_start", {
        "step": "pipeline",
        "description": "Starting Decision Support Agent...",
        "started_at": started_at,
        "agent_name": "Decision Support Pipeline",
        "agent_role": "4-2-1-1 multi-stage stock selection system",
    })

    # Collect log messages via callback
    logs: list[str] = []

    def make_logger(step_name: str):
        def log_fn(msg: str):
            logs.append(msg)
            print(f"[DecisionSupport] [{step_name}] {msg}")
        return log_fn

    # ── Market Regime Detection ───────────────────────────────────────────
    market_regime = {"vix": None, "regime": "normal", "warning": None}
    try:
        broker = get_broker(access_token)
        kite = broker.raw_kite
        vix_quote = kite.quote(["NSE:INDIA VIX"])
        vix_data = vix_quote.get("NSE:INDIA VIX", {})
        vix_value = vix_data.get("last_price", 0)
        market_regime["vix"] = round(vix_value, 2)

        rsi_buy_limit = resolved.get("rsi_buy_limit", 30)
        if vix_value >= VIX_TIER3_THRESHOLD:
            market_regime["regime"] = "extreme_fear"
            market_regime["warning"] = (
                f"VIX at {vix_value:.1f} — EXTREME FEAR (>{VIX_TIER3_THRESHOLD}). "
                "Pipeline running in read-only mode; automation will be paused."
            )
            # Do not tighten RSI further — inform user but let the scan proceed
            resolved["rsi_buy_limit"] = max(20, rsi_buy_limit - VIX_TIER2_RSI_TIGHTEN)
        elif vix_value >= VIX_TIER2_THRESHOLD:
            market_regime["regime"] = "high_fear"
            market_regime["warning"] = (
                f"VIX at {vix_value:.1f} — HIGH FEAR ({VIX_TIER2_THRESHOLD}–{VIX_TIER3_THRESHOLD}). "
                f"Tightening RSI thresholds by {VIX_TIER2_RSI_TIGHTEN} points. Prefer Gear 1-3 only."
            )
            resolved["rsi_buy_limit"] = max(20, rsi_buy_limit - VIX_TIER2_RSI_TIGHTEN)
        elif vix_value >= VIX_TIER1_THRESHOLD:
            market_regime["regime"] = "fearful"
            market_regime["warning"] = (
                f"VIX at {vix_value:.1f} — elevated fear ({VIX_TIER1_THRESHOLD}–{VIX_TIER2_THRESHOLD}). "
                f"Tightening RSI thresholds by {VIX_TIER1_RSI_TIGHTEN} points."
            )
            resolved["rsi_buy_limit"] = max(20, rsi_buy_limit - VIX_TIER1_RSI_TIGHTEN)
    except Exception as e:
        print(f"[DecisionSupport] VIX fetch failed: {e}")

    yield _sse("step_log", {
        "step": "pipeline",
        "message": f"Market regime: {market_regime['regime'].upper()} (VIX: {market_regime.get('vix', 'N/A')})",
    })

    # ── Step 1: Market Scanner ───────────────────────────────────────────
    universe_key = resolved.get("universe", "nifty500")
    universe_label = universe_key.replace("_", " ").title()
    step1_started = time.monotonic()
    yield _sse("step_start", {
        "step": "universe_filter",
        "agent_name": "Market Scanner",
        "agent_role": "Screens universe by volume, 200-EMA & relative strength vs Nifty",
        "description": f"Scanning {universe_label} universe — filtering by turnover, volume trend, 200-EMA & 3-month relative strength...",
        "started_at": datetime.now().isoformat(),
    })

    universe_stocks = []
    total_scanned = 0
    try:
        log_fn = make_logger("universe_filter")

        def universe_log(msg):
            log_fn(msg)

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

    # Extract total scanned from logs
    for msg in logs:
        if "list:" in msg and "stocks" in msg:
            try:
                total_scanned = int(msg.split("list:")[1].split("stocks")[0].strip())
            except (ValueError, IndexError):
                pass
            break
    if total_scanned == 0:
        total_scanned = len(universe_stocks) or 500

    for msg in logs:
        yield _sse("step_log", {"step": "universe_filter", "message": msg})
    logs.clear()

    step1_ms = int((time.monotonic() - step1_started) * 1000)
    yield _sse("step_complete", {
        "step": "universe_filter",
        "stocks_remaining": len(universe_stocks),
        "initial_count": total_scanned,
        "completed_at": datetime.now().isoformat(),
        "duration_ms": step1_ms,
    })

    if not universe_stocks:
        yield _sse("final_result", {
            "stocks": [],
            "total_scanned": total_scanned,
            "total_selected": 0,
            "market_regime": market_regime,
            "message": "No stocks passed the universe filter. Market conditions may be weak.",
            "completed_at": datetime.now().isoformat(),
        })
        return

    # ── Step 2: Quant Analyst ────────────────────────────────────────────
    step2_started = time.monotonic()
    yield _sse("step_start", {
        "step": "technical_setup",
        "agent_name": "Quant Analyst",
        "agent_role": "Identifies RSI entry triggers with ADX trend confirmation",
        "description": f"Running quantitative analysis on {len(universe_stocks)} stocks — checking ADX strength, 20-EMA position & RSI entry signals (pullback / momentum)...",
        "started_at": datetime.now().isoformat(),
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

    step2_ms = int((time.monotonic() - step2_started) * 1000)
    yield _sse("step_complete", {
        "step": "technical_setup",
        "stocks_remaining": len(technical_stocks),
        "previous_count": len(universe_stocks),
        "completed_at": datetime.now().isoformat(),
        "duration_ms": step2_ms,
    })

    if not technical_stocks:
        yield _sse("final_result", {
            "stocks": [],
            "total_scanned": total_scanned,
            "total_selected": 0,
            "market_regime": market_regime,
            "message": "No stocks have valid technical entry setups right now.",
            "completed_at": datetime.now().isoformat(),
        })
        return

    # ── Step 3: Fundamentals Analyst ─────────────────────────────────────
    step3_started = time.monotonic()
    yield _sse("step_start", {
        "step": "fundamentals",
        "agent_name": "Fundamentals Analyst",
        "agent_role": "Validates quarterly profit growth, ROE & debt levels via Screener.in",
        "description": f"Scraping Screener.in for {len(technical_stocks)} stocks — verifying YoY profit growth, ROE quality & D/E ratios...",
        "started_at": datetime.now().isoformat(),
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

    step3_ms = int((time.monotonic() - step3_started) * 1000)
    yield _sse("step_complete", {
        "step": "fundamentals",
        "stocks_remaining": len(fundamental_stocks),
        "previous_count": len(technical_stocks),
        "completed_at": datetime.now().isoformat(),
        "duration_ms": step3_ms,
    })

    if not fundamental_stocks:
        yield _sse("final_result", {
            "stocks": [],
            "total_scanned": total_scanned,
            "total_selected": 0,
            "market_regime": market_regime,
            "message": "No stocks show improving quarterly profits among technical picks.",
            "completed_at": datetime.now().isoformat(),
        })
        return

    # ── Step 4: Sector Momentum ──────────────────────────────────────────
    step4_started = time.monotonic()
    yield _sse("step_start", {
        "step": "sector_health",
        "agent_name": "Sector Momentum",
        "agent_role": "Confirms positive 5-day sector index tailwind via Kite API",
        "description": f"Measuring sector momentum for {len(fundamental_stocks)} stocks — fetching 5-day sector index performance from Kite API...",
        "started_at": datetime.now().isoformat(),
    })

    sector_stocks = []
    try:
        log_fn = make_logger("sector_health")
        sector_stocks = check_sector_health(access_token, fundamental_stocks, log=log_fn)
    except Exception as e:
        yield _sse("error", {"step": "sector_health", "message": str(e)})
        return

    for msg in logs:
        yield _sse("step_log", {"step": "sector_health", "message": msg})
    logs.clear()

    step4_ms = int((time.monotonic() - step4_started) * 1000)
    yield _sse("step_complete", {
        "step": "sector_health",
        "stocks_remaining": len(sector_stocks),
        "previous_count": len(fundamental_stocks),
        "completed_at": datetime.now().isoformat(),
        "duration_ms": step4_ms,
    })

    if not sector_stocks:
        yield _sse("final_result", {
            "stocks": [],
            "total_scanned": total_scanned,
            "total_selected": 0,
            "market_regime": market_regime,
            "message": "No stocks in sectors with positive momentum right now.",
            "completed_at": datetime.now().isoformat(),
        })
        return

    # ── Step 5: AI Conviction Engine ─────────────────────────────────────
    step5_started = time.monotonic()
    yield _sse("step_start", {
        "step": "ai_ranking",
        "agent_name": "AI Conviction Engine",
        "agent_role": "Composite scoring (Technical + Fundamental + RS + Volume) then LLM news sentiment ranking",
        "description": f"Running AI conviction engine on {len(sector_stocks)} stocks — computing composite scores, fetching news headlines & running LLM conviction ranking...",
        "started_at": datetime.now().isoformat(),
    })

    final_stocks = sector_stocks
    try:
        log_fn = make_logger("ai_ranking")

        # Composite scoring (rule-based, fast)
        final_stocks = compute_composite_scores(final_stocks, log=log_fn)

        # AI ranking with news (LLM-powered)
        final_stocks = ai_rank_stocks(final_stocks, market_regime, log=log_fn, llm_provider=llm_provider)
    except Exception as e:
        log_fn = make_logger("ai_ranking")
        log_fn(f"AI ranking failed, using composite scores only: {e}")

    for msg in logs:
        yield _sse("step_log", {"step": "ai_ranking", "message": msg})
    logs.clear()

    step5_ms = int((time.monotonic() - step5_started) * 1000)
    yield _sse("step_complete", {
        "step": "ai_ranking",
        "stocks_remaining": len(final_stocks),
        "previous_count": len(sector_stocks),
        "completed_at": datetime.now().isoformat(),
        "duration_ms": step5_ms,
    })

    # ── Step 6: Portfolio Ranker ──────────────────────────────────────────
    step6_started = time.monotonic()
    yield _sse("step_start", {
        "step": "final_ranking",
        "agent_name": "Portfolio Ranker",
        "agent_role": "Multi-factor final ranking across all 5 pipeline signals with LLM rank explanations",
        "description": (
            f"Ranking {len(final_stocks)} finalist{'s' if len(final_stocks) != 1 else ''} "
            "across 5 weighted dimensions (conviction, composite, RS, fundamentals, sector) "
            "and generating LLM rank explanations..."
        ),
        "started_at": datetime.now().isoformat(),
    })

    try:
        log_fn = make_logger("final_ranking")
        final_stocks = rank_final_shortlist(final_stocks, log=log_fn, llm_provider=llm_provider)
    except Exception as e:
        log_fn = make_logger("final_ranking")
        log_fn(f"Portfolio Ranker failed, stocks remain in AI conviction order: {e}")

    for msg in logs:
        yield _sse("step_log", {"step": "final_ranking", "message": msg})
    logs.clear()

    step6_ms = int((time.monotonic() - step6_started) * 1000)
    yield _sse("step_complete", {
        "step": "final_ranking",
        "stocks_remaining": len(final_stocks),
        "previous_count": len(final_stocks),
        "completed_at": datetime.now().isoformat(),
        "duration_ms": step6_ms,
    })

    # ── Final Result ─────────────────────────────────────────────────────
    result_stocks = []
    for s in final_stocks:
        result_stocks.append({
            "symbol": s.get("symbol"),
            "instrument_token": s.get("instrument_token"),
            "current_price": s.get("current_price"),
            "rsi": s.get("rsi"),
            "rsi_trigger": s.get("rsi_trigger"),
            "sector": s.get("sector"),
            "sector_5d_change": s.get("sector_5d_change"),
            "why_selected": s.get("why_selected", ""),
            "ema_20": s.get("ema_20"),
            "ema_200": s.get("ema_200"),
            "stock_3m_return": s.get("stock_3m_return"),
            "nifty_3m_return": s.get("nifty_3m_return"),
            "sector_3m_return": s.get("sector_3m_return"),
            "avg_volume_20d": s.get("avg_volume_20d"),
            "volume_ratio": s.get("volume_ratio"),
            "adx": s.get("adx"),
            "roe": s.get("roe"),
            "debt_to_equity": s.get("debt_to_equity"),
            "composite_score": s.get("composite_score"),
            "score_breakdown": s.get("score_breakdown"),
            "profit_yoy_growing": s.get("profit_yoy_growing"),
            "ai_conviction": s.get("ai_conviction"),
            "news_sentiment": s.get("news_sentiment"),
            "news_flag": s.get("news_flag"),
            "news_headlines": s.get("news_headlines", []),
            # Portfolio Ranker fields
            "final_rank": s.get("final_rank"),
            "final_rank_score": s.get("final_rank_score"),
            "rank_reason": s.get("rank_reason", ""),
            "rank_factors": s.get("rank_factors"),
            # Claude-only fields (None on Gemini path)
            "primary_risk": s.get("primary_risk"),
            "trade_type": s.get("trade_type"),
            "portfolio_note": s.get("portfolio_note"),
        })

    yield _sse("final_result", {
        "stocks": result_stocks,
        "total_scanned": total_scanned,
        "total_selected": len(result_stocks),
        "gear": gear,
        "gear_label": gear_profile.get("label", "Balanced"),
        "atr_stop_loss_multiplier": resolved.get("atr_stop_loss_multiplier", 1.5),
        "market_regime": market_regime,
        "message": (
            f"Pipeline complete: {len(result_stocks)} stocks selected from {total_scanned}."
            if result_stocks
            else "No stocks currently meet all criteria. The market may lack strong setups."
        ),
        "started_at": started_at,
        "completed_at": datetime.now().isoformat(),
    })
