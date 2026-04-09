"""Unified Stock Audit Pipeline — combines technical, fundamental, sector, and AI signals.

Replaces both the legacy StockHealthService (dashboard tiles) and the sell audit
pipeline (Discover page) into a single, persistent audit that runs once per user
request and saves results forever until re-triggered.

Score: 1–10 health score (10 = perfectly healthy, 1 = critical)
  Component weights:
    Technical Health    3.0  (RSI, ADX, EMA alignment, volume)
    Fundamental Health  2.5  (ROE, D/E, profit trend)
    Relative Strength   2.0  (3M vs Nifty + sector)
    News Sentiment      1.5  (Claude AI batch)
    Position Health     1.0  (unrealized P&L %)

Labels:
    7.0–10  → HEALTHY
    5.0–6.9 → STABLE
    3.0–4.9 → WATCH
    <3.0    → CRITICAL

LLM roles:
    Orchestration (supervisor/routing): OpenAI
    Financial analysis (all audit AI): Claude with extended thinking
"""

import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from typing import Callable, Optional

from agents.decision_support.sell_tools import fetch_portfolio_holdings
from agents.shared.data_infra import PipelineSession
from agents.shared.quant_agent import enrich_with_technicals
from agents.shared.fundamentals_agent import enrich_with_fundamentals
from agents.shared.sector_agent import enrich_with_sector
from agents.shared.news_agent import fetch_news_batch
from broker import get_broker
from constants import (
    NEWS_LOOKBACK_DAYS,
    AUDIT_HEALTHY,
    AUDIT_STABLE,
    AUDIT_WATCH,
    AUDIT_AI_THINKING_BUDGET,
)
from services.analysis_storage import save_analysis_result


# ---------------------------------------------------------------------------
# SSE helpers
# ---------------------------------------------------------------------------

def _sse(event: str, data: dict) -> str:
    """Format a single SSE message."""
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


# ---------------------------------------------------------------------------
# Stage 5: Rule-based health scoring (1–10)
# ---------------------------------------------------------------------------

def compute_health_scores(holdings: list[dict]) -> list[dict]:
    """Convert raw technical/fundamental/sector data into a positive 1–10 health score.

    Returns the same list with added keys:
        health_score (float 1–10)
        health_label ('HEALTHY'|'STABLE'|'WATCH'|'CRITICAL')
        health_components (dict with 5 component scores; news=placeholder 0.75)
    """
    for h in holdings:
        price = h.get("current_price", 0) or 0

        # ── Technical Health (0–3.0) ──────────────────────────────────────
        tech = 0.0
        ema200 = h.get("ema_200")
        ema50  = h.get("ema_50")
        ema20  = h.get("ema_20")
        if ema200 and price > ema200:
            tech += 0.6   # long-term trend intact
        if ema50 and price > ema50:
            tech += 0.5   # medium-term trend intact
        if ema20 and price > ema20:
            tech += 0.3   # short-term trend intact
        rsi = h.get("rsi")
        if rsi is not None:
            if 40 <= rsi <= 65:
                tech += 0.7   # healthy momentum zone
            elif (30 <= rsi < 40) or (65 < rsi <= 75):
                tech += 0.3   # slightly stretched but acceptable
        adx = h.get("adx")
        if adx is not None and adx >= 25:
            tech += 0.4   # confirmed trending market
        vr = h.get("volume_ratio")
        if vr is not None:
            if vr >= 0.8:
                tech += 0.5   # healthy volume participation
            elif vr >= 0.6:
                tech += 0.2
        tech = min(3.0, round(tech, 2))

        # ── Fundamental Health (0–2.5) ────────────────────────────────────
        fund = 0.0
        roe = h.get("roe")
        de  = h.get("debt_to_equity")
        if roe is not None:
            if roe >= 15:   fund += 1.0
            elif roe >= 10: fund += 0.6
            elif roe >= 5:  fund += 0.3
        if de is not None:
            if de < 1.0:   fund += 0.8
            elif de < 2.0: fund += 0.4
            elif de < 3.0: fund += 0.1
        pdc  = h.get("profit_declining_quarters", 0) or 0
        qoq  = h.get("qoq_declining", False)
        if pdc == 0 and not qoq:
            fund += 0.5   # no profit deterioration
        elif pdc <= 1 and not qoq:
            fund += 0.2   # mild and temporary
        fund = min(2.5, round(fund, 2))

        # ── Relative Strength (0–2.0) ─────────────────────────────────────
        rs   = 0.0
        s3m  = h.get("stock_3m_return")
        n3m  = h.get("nifty_3m_return") or 0
        sec3m = h.get("sector_3m_return") or 0
        sec5d = h.get("sector_5d_change") or 0
        if s3m is not None:
            gap_n = s3m - n3m
            if gap_n >= 5:    rs += 0.7
            elif gap_n >= 0:  rs += 0.4
            elif gap_n >= -5: rs += 0.2
            gap_s = s3m - sec3m
            if gap_s >= 2:    rs += 0.6
            elif gap_s >= -2: rs += 0.35
            elif gap_s >= -5: rs += 0.1
        if sec5d >= 0:    rs += 0.5
        elif sec5d >= -1: rs += 0.2
        rs = min(2.0, round(rs, 2))

        # ── Position Health (0–1.0) ───────────────────────────────────────
        pnl_pct = h.get("pnl_percentage", 0) or 0
        if pnl_pct >= 15:    pos = 1.0
        elif pnl_pct >= 5:   pos = 0.8
        elif pnl_pct >= 0:   pos = 0.6
        elif pnl_pct >= -5:  pos = 0.4
        elif pnl_pct >= -15: pos = 0.1
        else:                pos = 0.0
        pos = round(pos, 2)

        # ── News placeholder (0–1.5) — filled by Stage 6 AI ──────────────
        news = 0.75   # neutral default until AI enriches

        raw_score    = tech + fund + rs + news + pos
        health_score = max(1.0, min(10.0, round(raw_score, 1)))

        if health_score >= AUDIT_HEALTHY:   label = "HEALTHY"
        elif health_score >= AUDIT_STABLE:  label = "STABLE"
        elif health_score >= AUDIT_WATCH:   label = "WATCH"
        else:                               label = "CRITICAL"

        h["health_score"]      = health_score
        h["health_label"]      = label
        h["health_components"] = {
            "technical":         tech,
            "fundamental":       fund,
            "relative_strength": rs,
            "news":              news,
            "position":          pos,
        }

    return holdings


# ---------------------------------------------------------------------------
# Stage 6: Claude AI batch enrichment
# ---------------------------------------------------------------------------

def ai_enrich_audit(
    holdings: list[dict],
    llm_provider: Optional[str],
    log: Callable[[str], None] = print,
    user_id: Optional[int] = None,
) -> list[dict]:
    """Batch Claude call for news analysis + holistic health verdicts.

    Fetches recent news for all holdings in parallel, then calls Claude with
    extended thinking to assess each stock's health and provide:
        news_score       (1–5; maps to 0–1.5 on health score)
        audit_verdict    ('HOLD'|'MONITOR'|'CONSIDER_EXIT'|'EXIT')
        key_risks        (list[str])
        key_positives    (list[str])
        ai_reasoning     (str, 2–3 sentences)

    Updates health_score and health_label after incorporating news_score.
    """
    from agents.config import get_llm

    # Fetch news for all holdings in parallel via shared news_agent
    symbols = [h["symbol"] for h in holdings]
    news_map = fetch_news_batch(symbols, log=log)
    log("News fetched. Sending to Claude AI for holistic health assessment...")

    # Build context lines per holding
    holding_lines = []
    for h in sorted(holdings, key=lambda x: x.get("health_score", 5)):
        comp  = h.get("health_components", {})
        heads = news_map.get(h["symbol"], [])
        news_text = "; ".join(x["title"] for x in heads[:4]) or "No recent news found"
        price = h.get("current_price", 0)

        ema_align = "Bullish"
        ema200 = h.get("ema_200")
        ema50  = h.get("ema_50")
        if ema200 and price < ema200:
            ema_align = "Bearish"
        elif ema50 and price < ema50:
            ema_align = "Mixed"

        holding_lines.append(
            f"- {h['symbol']}: Score={h.get('health_score')}/10 ({h.get('health_label')}), "
            f"Tech={comp.get('technical')}/3.0, Fund={comp.get('fundamental')}/2.5, "
            f"RS={comp.get('relative_strength')}/2.0, Pos={comp.get('position')}/1.0, "
            f"P&L={h.get('pnl_percentage')}%, "
            f"RSI={h.get('rsi')}, ADX={h.get('adx')}, EMA={ema_align}, "
            f"ROE={h.get('roe', 'N/A')}%, D/E={h.get('debt_to_equity', 'N/A')}, "
            f"ProfitDeclining={h.get('profit_declining_quarters', 0)} qtrs, "
            f"3M: stock={h.get('stock_3m_return', 'N/A')}% vs nifty={h.get('nifty_3m_return', 'N/A')}%, "
            f"News: {news_text}"
        )

    effective_provider = llm_provider if llm_provider else "claude"
    if effective_provider == "claude":
        llm = get_llm(
            temperature=0.1,
            provider="claude",
            extended_thinking=True,
            thinking_budget=AUDIT_AI_THINKING_BUDGET,
            user_id=user_id,
            pipeline="audit",
        )
    else:
        llm = get_llm(temperature=0.3, provider=effective_provider, user_id=user_id, pipeline="audit")

    prompt = (
        "You are a senior portfolio health analyst specializing in Indian NSE equity holdings.\n\n"
        "Review each holding holistically — technical signals, fundamentals, relative strength, "
        "current P&L, and news — then provide a clear health verdict.\n\n"
        "Holdings (sorted by health score, lowest first):\n"
        + "\n".join(holding_lines)
        + "\n\nFor EACH holding, return a JSON object with these exact keys:\n"
        "{\n"
        '  "symbol": "<symbol>",\n'
        '  "news_score": <integer 1-5>,\n'
        '  "audit_verdict": "HOLD" | "MONITOR" | "CONSIDER_EXIT" | "EXIT",\n'
        '  "key_risks": ["<specific risk 1>", "<specific risk 2>"],\n'
        '  "key_positives": ["<specific positive 1>", "<specific positive 2>"],\n'
        '  "ai_reasoning": "<2-3 sentences: most important health driver and overall outlook>"\n'
        "}\n\n"
        "Verdict guide:\n"
        "HOLD         = Strong or stable health, no action needed\n"
        "MONITOR      = Acceptable but emerging concerns, watch closely\n"
        "CONSIDER_EXIT = Material deterioration in multiple dimensions\n"
        "EXIT         = Immediate exit warranted based on signals\n\n"
        "news_score: 5=very positive news, 3=neutral, 1=very negative/alarming news\n\n"
        "Return ONLY a valid JSON array of these objects. No markdown, no extra text."
    )

    try:
        response = llm.invoke(prompt)
        content  = response.content.strip()
        if "```" in content:
            parts   = content.split("```")
            content = parts[1] if len(parts) > 1 else content
            if content.startswith("json"):
                content = content[4:]
            content = content.strip()
        results    = json.loads(content)
        result_map = {r["symbol"]: r for r in results}

        for h in holdings:
            r          = result_map.get(h["symbol"], {})
            news_score = max(1, min(5, int(r.get("news_score", 3))))
            # Map 1–5 → 0.0–1.5 linearly
            news_comp  = round((news_score - 1) / 4 * 1.5, 2)

            h["health_components"]["news"] = news_comp
            raw          = sum(h["health_components"].values())
            health_score = max(1.0, min(10.0, round(raw, 1)))

            if health_score >= AUDIT_HEALTHY:   label = "HEALTHY"
            elif health_score >= AUDIT_STABLE:  label = "STABLE"
            elif health_score >= AUDIT_WATCH:   label = "WATCH"
            else:                               label = "CRITICAL"

            h["health_score"]   = health_score
            h["health_label"]   = label
            h["audit_verdict"]  = r.get("audit_verdict", "MONITOR")
            h["key_risks"]      = r.get("key_risks", [])
            h["key_positives"]  = r.get("key_positives", [])
            h["ai_reasoning"]   = r.get("ai_reasoning", "")
            h["news_score"]     = news_score
            h["news_headlines"] = [x["title"] for x in news_map.get(h["symbol"], [])[:3]]

        log(f"AI health assessment complete for {len(holdings)} holdings.")

    except Exception as e:
        log(f"AI enrichment failed ({e}). Using rule-based scores only.")
        for h in holdings:
            h["audit_verdict"]  = "MONITOR" if h.get("health_score", 5) < 5 else "HOLD"
            h["key_risks"]      = []
            h["key_positives"]  = []
            h["ai_reasoning"]   = ""
            h["news_score"]     = 3
            h["news_headlines"] = [x["title"] for x in news_map.get(h["symbol"], [])[:3]]

    return holdings


# ---------------------------------------------------------------------------
# Main pipeline entry point
# ---------------------------------------------------------------------------

def run_stock_audit(
    access_token: str,
    user_id: int,
    llm_provider: Optional[str] = None,
) -> "generator[str, None, None]":
    """Run the unified Stock Audit and yield SSE events.

    Stages:
        1. Portfolio Inspector   — fetch holdings + resolve tokens + sector lookup
        2. Quant Analyst         — RSI, ADX, EMA-20/50/200, ATR, 3M relative strength
        3. Fundamentals Analyst  — ROE, D/E, profit trends from Screener.in
        4. Sector Monitor        — 5-day sector index momentum
        5. Health Scorer         — rule-based 1–10 health score per stock
        6. AI Health Analyst     — Claude extended thinking for news + verdict
        7. Persist               — save results to user_analysis_cache SQLite table
    """
    session = PipelineSession()
    started_at = datetime.now().isoformat()

    def _emit(event: str, data: dict) -> str:
        return _sse(event, data)

    def _log_event(msg: str) -> str:
        return _emit("step_log", {"message": msg})

    # ── Stage 1: Portfolio Inspector ────────────────────────────────────
    yield _emit("step_start", {
        "step": 1,
        "agent": "Portfolio Inspector",
        "role": "Fetching live portfolio holdings and resolving instrument tokens",
    })
    logs_1 = []
    holdings = fetch_portfolio_holdings(
        access_token,
        log=lambda m: logs_1.append(m),
        session=session,
    )
    for msg in logs_1:
        yield _log_event(msg)
    yield _emit("step_complete", {"step": 1, "holdings_count": len(holdings)})

    if not holdings:
        yield _emit("final_result", {
            "holdings": [],
            "summary": {"total": 0, "healthy": 0, "stable": 0, "watch": 0, "critical": 0, "avg_score": 0},
            "message": "No holdings found in portfolio.",
            "started_at": started_at,
            "completed_at": datetime.now().isoformat(),
        })
        return

    # ── Stage 2: Quant Analyst ───────────────────────────────────────────
    yield _emit("step_start", {
        "step": 2,
        "agent": "Quant Analyst",
        "role": "Computing RSI, ADX, EMA-20/50/200, ATR and 3-month relative strength",
    })
    broker = get_broker(access_token)
    logs_2 = []
    holdings = enrich_with_technicals(
        holdings,
        broker.raw_kite,
        log=lambda m: logs_2.append(m),
        mode="enrich",
        session=session,
    )
    for msg in logs_2:
        yield _log_event(msg)
    yield _emit("step_complete", {"step": 2})

    # ── Stage 3: Fundamentals Analyst ────────────────────────────────────
    yield _emit("step_start", {
        "step": 3,
        "agent": "Fundamentals Analyst",
        "role": "Scraping Screener.in for quarterly profit trends, ROE and D/E ratios",
    })
    logs_3 = []
    holdings = enrich_with_fundamentals(
        holdings,
        log=lambda m: logs_3.append(m),
        mode="enrich",
        session=session,
    )
    for msg in logs_3:
        yield _log_event(msg)
    yield _emit("step_complete", {"step": 3})

    # ── Stage 4: Sector Monitor ──────────────────────────────────────────
    yield _emit("step_start", {
        "step": 4,
        "agent": "Sector Monitor",
        "role": "Measuring 5-day sector index performance",
    })
    logs_4 = []
    holdings = enrich_with_sector(
        holdings,
        broker.raw_kite,
        log=lambda m: logs_4.append(m),
        mode="enrich",
        include_3m=True,
        session=session,
    )
    for msg in logs_4:
        yield _log_event(msg)
    yield _emit("step_complete", {"step": 4})

    # ── Stage 5: Health Scorer ───────────────────────────────────────────
    yield _emit("step_start", {
        "step": 5,
        "agent": "Health Scorer",
        "role": "Computing rule-based 1–10 health score from all collected signals",
    })
    holdings = compute_health_scores(holdings)
    yield _emit("step_complete", {"step": 5})

    # ── Stage 6: AI Health Analyst ───────────────────────────────────────
    yield _emit("step_start", {
        "step": 6,
        "agent": "AI Health Analyst",
        "role": "Claude AI: news enrichment + holistic health verdict for each stock",
    })
    ai_logs: list[str] = []
    holdings = ai_enrich_audit(
        holdings,
        llm_provider,
        log=lambda m: ai_logs.append(m),
        user_id=user_id,
    )
    for msg in ai_logs:
        yield _log_event(msg)
    yield _emit("step_complete", {"step": 6})

    # ── Stage 7: Persist results ─────────────────────────────────────────
    saved_at = datetime.now().isoformat()
    for h in holdings:
        # Strip private/internal fields before storing
        record = {k: v for k, v in h.items() if not k.startswith("_")}
        record["type"]     = "audit"
        record["saved_at"] = saved_at
        save_analysis_result(user_id, h["symbol"], record)

    # ── Summary ──────────────────────────────────────────────────────────
    healthy  = sum(1 for h in holdings if h.get("health_label") == "HEALTHY")
    stable   = sum(1 for h in holdings if h.get("health_label") == "STABLE")
    watch    = sum(1 for h in holdings if h.get("health_label") == "WATCH")
    critical = sum(1 for h in holdings if h.get("health_label") == "CRITICAL")
    avg_score = round(
        sum(h.get("health_score", 5.0) for h in holdings) / len(holdings), 1
    )

    # Sort: critical first, healthy last
    holdings.sort(key=lambda h: h.get("health_score", 5.0))

    yield _emit("final_result", {
        "holdings": holdings,
        "summary": {
            "total":    len(holdings),
            "healthy":  healthy,
            "stable":   stable,
            "watch":    watch,
            "critical": critical,
            "avg_score": avg_score,
        },
        "message": f"Audit complete — {len(holdings)} stocks analysed.",
        "started_at":    started_at,
        "completed_at":  datetime.now().isoformat(),
    })
