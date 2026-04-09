"""SSE streaming generator for the Sell Analysis pipeline.

Analyzes the user's current portfolio holdings for sell urgency.
Streams Server-Sent Events at each stage so the frontend can display
a live progress stepper.

Stages:
  1. Portfolio Inspector  — fetch live holdings + resolve tokens + sector
  2. Quant Analyst        — RSI, ADX, EMA-20/50/200, ATR, 3M relative strength
  3. Fundamentals Analyst — quarterly profit trends, ROE, D/E from Screener.in
  4. Sector Monitor       — 5-day sector index performance
  5. Sell Signal Engine   — urgency scoring + AI sell/hold reasoning
"""

import json
import time
from datetime import datetime

from agents.decision_support.sell_tools import (
    fetch_portfolio_holdings,
    enrich_holdings_with_technicals,
    enrich_holdings_with_fundamentals,
    enrich_holdings_with_sector,
    compute_sell_scores,
    ai_rank_sell_candidates,
)
from agents.shared.data_infra import PipelineSession
from broker import get_broker
from constants import VIX_HIGH_THRESHOLD


def _sse(event: str, data: dict) -> str:
    """Format a Server-Sent Event string."""
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


def run_sell_pipeline_stream(access_token: str, config: dict | None = None, user_id: int | None = None):
    """Generator yielding SSE events as the sell analysis pipeline runs.

    Args:
        access_token: Kite Connect access token.
        config: Optional config dict. Supports 'llm_provider' ('claude'|'openai').
                Claude is the default for sell analysis.

    Events emitted:
        step_start    — a pipeline stage is beginning
        step_log      — intermediate progress message
        step_complete — a stage finished
        final_result  — all holdings with sell urgency scores sorted desc
        error         — a fatal failure
    """
    if config is None:
        config = {}

    llm_provider = config.get("llm_provider", "claude")  # Claude is default for sell
    started_at = datetime.now().isoformat()

    session = PipelineSession()

    yield _sse("step_start", {
        "step": "pipeline",
        "description": "Starting Portfolio Sell Analysis...",
        "started_at": started_at,
        "agent_name": "Sell Analysis Pipeline",
        "agent_role": "Portfolio audit — identifies holdings to exit based on technical deterioration, relative weakness & fundamentals",
    })

    logs: list[str] = []

    def make_logger(step_name: str):
        def log_fn(msg: str):
            logs.append(msg)
            print(f"[SellPipeline] [{step_name}] {msg}")
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
        if vix_value > VIX_HIGH_THRESHOLD:
            market_regime["regime"] = "fearful"
            market_regime["warning"] = (
                f"VIX at {vix_value:.1f} (elevated fear). "
                "High volatility increases sell urgency for weak positions."
            )
    except Exception as e:
        print(f"[SellPipeline] VIX fetch failed: {e}")

    yield _sse("step_log", {
        "step": "pipeline",
        "message": f"Market regime: {market_regime['regime'].upper()} (VIX: {market_regime.get('vix', 'N/A')})",
    })

    # ── Stage 1: Portfolio Inspector ─────────────────────────────────────
    step1_started = time.monotonic()
    yield _sse("step_start", {
        "step": "portfolio_load",
        "agent_name": "Portfolio Inspector",
        "agent_role": "Fetches live holdings from Zerodha Kite and resolves instrument tokens & sector mapping",
        "description": "Loading live portfolio holdings from Kite API...",
        "started_at": datetime.now().isoformat(),
    })

    holdings = []
    try:
        log_fn = make_logger("portfolio_load")
        holdings = fetch_portfolio_holdings(access_token, log=log_fn, session=session)
    except Exception as e:
        yield _sse("error", {"step": "portfolio_load", "message": str(e)})
        return

    for msg in logs:
        yield _sse("step_log", {"step": "portfolio_load", "message": msg})
    logs.clear()

    step1_ms = int((time.monotonic() - step1_started) * 1000)
    yield _sse("step_complete", {
        "step": "portfolio_load",
        "holdings_count": len(holdings),
        "completed_at": datetime.now().isoformat(),
        "duration_ms": step1_ms,
    })

    if not holdings:
        yield _sse("final_result", {
            "holdings": [],
            "total_holdings": 0,
            "strong_sell_count": 0, "sell_count": 0,
            "watch_count": 0, "hold_count": 0,
            "market_regime": market_regime,
            "message": "No holdings found in portfolio. Add positions to Zerodha first.",
            "started_at": started_at,
            "completed_at": datetime.now().isoformat(),
        })
        return

    # ── Stage 2: Quant Analyst ───────────────────────────────────────────
    step2_started = time.monotonic()
    yield _sse("step_start", {
        "step": "technical_scan",
        "agent_name": "Quant Analyst",
        "agent_role": "Fetches 400-day OHLCV history and computes RSI, ADX, EMA-20/50/200, ATR, 3M relative strength vs Nifty",
        "description": f"Running quantitative analysis on {len(holdings)} holdings — fetching historical data and computing technical indicators...",
        "started_at": datetime.now().isoformat(),
    })

    try:
        log_fn = make_logger("technical_scan")
        broker = get_broker(access_token)
        kite = broker.raw_kite
        holdings = enrich_holdings_with_technicals(holdings, kite, log=log_fn, session=session)
    except Exception as e:
        yield _sse("error", {"step": "technical_scan", "message": str(e)})
        return

    for msg in logs:
        yield _sse("step_log", {"step": "technical_scan", "message": msg})
    logs.clear()

    step2_ms = int((time.monotonic() - step2_started) * 1000)
    yield _sse("step_complete", {
        "step": "technical_scan",
        "holdings_count": len(holdings),
        "completed_at": datetime.now().isoformat(),
        "duration_ms": step2_ms,
    })

    # ── Stage 3: Fundamentals Analyst ────────────────────────────────────
    step3_started = time.monotonic()
    yield _sse("step_start", {
        "step": "fundamental_scan",
        "agent_name": "Fundamentals Analyst",
        "agent_role": "Scrapes Screener.in for quarterly profit trends, ROE, and D/E ratios",
        "description": f"Scraping Screener.in for {len(holdings)} holdings — checking quarterly profit trajectory, ROE quality & leverage...",
        "started_at": datetime.now().isoformat(),
    })

    try:
        log_fn = make_logger("fundamental_scan")
        holdings = enrich_holdings_with_fundamentals(holdings, log=log_fn, session=session)
    except Exception as e:
        yield _sse("error", {"step": "fundamental_scan", "message": str(e)})
        return

    for msg in logs:
        yield _sse("step_log", {"step": "fundamental_scan", "message": msg})
    logs.clear()

    step3_ms = int((time.monotonic() - step3_started) * 1000)
    yield _sse("step_complete", {
        "step": "fundamental_scan",
        "holdings_count": len(holdings),
        "completed_at": datetime.now().isoformat(),
        "duration_ms": step3_ms,
    })

    # ── Stage 4: Sector Monitor ──────────────────────────────────────────
    step4_started = time.monotonic()
    yield _sse("step_start", {
        "step": "sector_check",
        "agent_name": "Sector Monitor",
        "agent_role": "Measures 5-day sector index performance to identify sector-level headwinds",
        "description": f"Fetching sector index performance for {len(holdings)} holdings — measuring 5-day sector tailwinds and headwinds...",
        "started_at": datetime.now().isoformat(),
    })

    try:
        log_fn = make_logger("sector_check")
        holdings = enrich_holdings_with_sector(holdings, access_token, log=log_fn, session=session)
    except Exception as e:
        yield _sse("error", {"step": "sector_check", "message": str(e)})
        return

    for msg in logs:
        yield _sse("step_log", {"step": "sector_check", "message": msg})
    logs.clear()

    step4_ms = int((time.monotonic() - step4_started) * 1000)
    yield _sse("step_complete", {
        "step": "sector_check",
        "holdings_count": len(holdings),
        "completed_at": datetime.now().isoformat(),
        "duration_ms": step4_ms,
    })

    # ── Stage 5: Sell Signal Engine ──────────────────────────────────────
    step5_started = time.monotonic()
    yield _sse("step_start", {
        "step": "sell_scoring",
        "agent_name": "Sell Signal Engine",
        "agent_role": "Multi-factor sell urgency scoring (Technical + Relative Strength + Fundamentals + P&L) with AI exit reasoning",
        "description": f"Computing sell urgency scores for {len(holdings)} holdings and generating AI exit/hold reasoning...",
        "started_at": datetime.now().isoformat(),
    })

    try:
        log_fn = make_logger("sell_scoring")
        holdings = compute_sell_scores(holdings, log=log_fn, session=session)
        holdings = ai_rank_sell_candidates(holdings, market_regime, log=log_fn, llm_provider=llm_provider, user_id=user_id, session=session)
    except Exception as e:
        log_fn = make_logger("sell_scoring")
        log_fn(f"Sell scoring failed, using rule-based scores only: {e}")
        holdings = compute_sell_scores(holdings, session=session)

    for msg in logs:
        yield _sse("step_log", {"step": "sell_scoring", "message": msg})
    logs.clear()

    step5_ms = int((time.monotonic() - step5_started) * 1000)
    yield _sse("step_complete", {
        "step": "sell_scoring",
        "holdings_count": len(holdings),
        "completed_at": datetime.now().isoformat(),
        "duration_ms": step5_ms,
    })

    # ── Final Result ─────────────────────────────────────────────────────
    strong_sell = sum(1 for h in holdings if h.get("sell_urgency_label") == "STRONG SELL")
    sell = sum(1 for h in holdings if h.get("sell_urgency_label") == "SELL")
    watch = sum(1 for h in holdings if h.get("sell_urgency_label") == "WATCH")
    hold = sum(1 for h in holdings if h.get("sell_urgency_label") == "HOLD")

    result_holdings = []
    for h in holdings:
        result_holdings.append({
            # Portfolio data
            "symbol": h.get("symbol"),
            "exchange": h.get("exchange"),
            "quantity": h.get("quantity"),
            "average_price": h.get("average_price"),
            "last_price": h.get("last_price"),
            "pnl": h.get("pnl"),
            "pnl_percentage": h.get("pnl_percentage"),
            "instrument_token": h.get("instrument_token"),
            # Technicals
            "current_price": h.get("current_price"),
            "rsi": h.get("rsi"),
            "adx": h.get("adx"),
            "ema_20": h.get("ema_20"),
            "ema_50": h.get("ema_50"),
            "ema_200": h.get("ema_200"),
            "atr": h.get("atr"),
            "stock_3m_return": h.get("stock_3m_return"),
            "nifty_3m_return": h.get("nifty_3m_return"),
            "avg_volume_20d": h.get("avg_volume_20d"),
            "volume_ratio": h.get("volume_ratio"),
            # Sector
            "sector": h.get("sector"),
            "sector_index": h.get("sector_index"),
            "sector_3m_return": h.get("sector_3m_return"),
            "sector_5d_change": h.get("sector_5d_change"),
            # Fundamentals
            "roe": h.get("roe"),
            "debt_to_equity": h.get("debt_to_equity"),
            "profit_declining_quarters": h.get("profit_declining_quarters"),
            "qoq_declining": h.get("qoq_declining"),
            "yoy_declining": h.get("yoy_declining"),
            # Sell scoring
            "sell_urgency_score": h.get("sell_urgency_score"),
            "sell_urgency_label": h.get("sell_urgency_label"),
            "sell_signals": h.get("sell_signals", []),
            "sell_score_breakdown": h.get("sell_score_breakdown"),
            # AI reasoning
            "sell_ai_conviction": h.get("sell_ai_conviction"),
            "sell_reason": h.get("sell_reason", ""),
            "hold_reason": h.get("hold_reason", ""),
            "news_sentiment": h.get("news_sentiment"),
            "news_flag": h.get("news_flag"),
            "news_headlines": h.get("news_headlines", []),
            # Note: _rsi_history is intentionally excluded from output
        })

    flagged_count = strong_sell + sell
    yield _sse("final_result", {
        "holdings": result_holdings,
        "total_holdings": len(result_holdings),
        "strong_sell_count": strong_sell,
        "sell_count": sell,
        "watch_count": watch,
        "hold_count": hold,
        "market_regime": market_regime,
        "message": (
            f"Sell analysis complete: {flagged_count} holding{'s' if flagged_count != 1 else ''} flagged for exit "
            f"({strong_sell} strong sell, {sell} sell, {watch} watch, {hold} hold)."
        ),
        "started_at": started_at,
        "completed_at": datetime.now().isoformat(),
    })
