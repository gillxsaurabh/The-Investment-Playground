"""Stage 1 — Cohort Builder (deterministic, no LLM).

Groups closed trades into analytical cohorts and computes aggregate statistics
that inform all subsequent LLM stages.
"""

import json
import math
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any, Dict, List, Tuple


def build_cohorts(trades: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Compute cohort aggregates across all closed trades.

    Returns a dict with keys:
        summary          — overall win/loss/pnl stats
        by_gear          — per-gear aggregates
        by_conviction    — aggregated by conviction tier (1-3 / 4-6 / 7-8 / 9-10)
        by_composite     — aggregated by composite score bucket (0-25 / 25-50 / 50-75 / 75-100)
        by_rsi_trigger   — pullback vs momentum
        by_sector        — per-sector aggregates
        by_exit_reason   — trailing stop / manual / audit-driven
        winners          — trades with realized_pnl_pct > 2%
        losers           — trades with realized_pnl_pct < -2%
        stopped_out      — trailing stop exits with negative pnl
        audit_exits      — trades where exit_audit_id is not null
        conviction_calibration — list of (conviction, pnl_pct) tuples for correlation
    """
    if not trades:
        return {"summary": {"trades": 0}, "winners": [], "losers": [],
                "stopped_out": [], "audit_exits": []}

    winners = [t for t in trades if (t.get("realized_pnl_pct") or 0) > 2]
    losers = [t for t in trades if (t.get("realized_pnl_pct") or 0) < -2]
    stopped_out = [t for t in trades
                   if t.get("exit_reason") == "Trailing Stop Hit"
                   and (t.get("realized_pnl_pct") or 0) < 0]
    audit_exits = [t for t in trades if t.get("exit_audit_id")]

    total_pnl = sum(t.get("realized_pnl_pct") or 0 for t in trades)
    avg_pnl = total_pnl / len(trades)
    win_rate = len(winners) / len(trades) * 100

    def _agg(group: List[Dict]) -> Dict:
        if not group:
            return {"count": 0}
        pnls = [t.get("realized_pnl_pct") or 0 for t in group]
        wins = sum(1 for p in pnls if p > 2)
        holds = [t.get("holding_days") or 0 for t in group]
        return {
            "count": len(group),
            "win_rate_pct": round(wins / len(group) * 100, 1),
            "avg_pnl_pct": round(sum(pnls) / len(pnls), 2),
            "total_pnl_pct": round(sum(pnls), 2),
            "avg_holding_days": round(sum(holds) / len(holds), 1) if holds else 0,
        }

    # By gear
    by_gear: Dict[str, List] = defaultdict(list)
    for t in trades:
        gear = str(t.get("gear_at_entry") or "unknown")
        by_gear[gear].append(t)

    # By conviction tier
    def _conviction_tier(c):
        if c is None:
            return "unknown"
        c = int(c)
        if c <= 3:
            return "1-3 (low)"
        if c <= 6:
            return "4-6 (medium)"
        if c <= 8:
            return "7-8 (high)"
        return "9-10 (very high)"

    by_conviction: Dict[str, List] = defaultdict(list)
    for t in trades:
        tier = _conviction_tier(t.get("scan_ai_conviction"))
        by_conviction[tier].append(t)

    # By composite score bucket
    def _composite_bucket(s):
        if s is None:
            return "unknown"
        s = float(s)
        if s < 25:
            return "0-25"
        if s < 50:
            return "25-50"
        if s < 75:
            return "50-75"
        return "75-100"

    by_composite: Dict[str, List] = defaultdict(list)
    for t in trades:
        bucket = _composite_bucket(t.get("scan_composite_score"))
        by_composite[bucket].append(t)

    # By RSI trigger
    by_trigger: Dict[str, List] = defaultdict(list)
    for t in trades:
        trigger = t.get("scan_rsi_trigger") or "unknown"
        by_trigger[trigger].append(t)

    # By sector
    by_sector: Dict[str, List] = defaultdict(list)
    for t in trades:
        sector = t.get("sector") or "unknown"
        by_sector[sector].append(t)

    # By exit reason
    by_exit: Dict[str, List] = defaultdict(list)
    for t in trades:
        reason = t.get("exit_reason") or "unknown"
        by_exit[reason].append(t)

    # Conviction calibration pairs
    conviction_cal = [
        {"conviction": t.get("scan_ai_conviction"), "pnl_pct": t.get("realized_pnl_pct")}
        for t in trades
        if t.get("scan_ai_conviction") is not None and t.get("realized_pnl_pct") is not None
    ]

    # Pearson correlation conviction vs pnl
    corr = None
    if len(conviction_cal) >= 3:
        xs = [c["conviction"] for c in conviction_cal]
        ys = [c["pnl_pct"] for c in conviction_cal]
        n = len(xs)
        mx, my = sum(xs) / n, sum(ys) / n
        num = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
        denom = math.sqrt(
            sum((x - mx) ** 2 for x in xs) * sum((y - my) ** 2 for y in ys)
        )
        corr = round(num / denom, 3) if denom else None

    return {
        "summary": {
            "trades": len(trades),
            "winners": len(winners),
            "losers": len(losers),
            "win_rate_pct": round(win_rate, 1),
            "avg_pnl_pct": round(avg_pnl, 2),
            "total_pnl_pct": round(total_pnl, 2),
            "stopped_out_count": len(stopped_out),
            "audit_exits_count": len(audit_exits),
        },
        "by_gear": {k: _agg(v) for k, v in by_gear.items()},
        "by_conviction": {k: _agg(v) for k, v in by_conviction.items()},
        "by_composite": {k: _agg(v) for k, v in by_composite.items()},
        "by_rsi_trigger": {k: _agg(v) for k, v in by_trigger.items()},
        "by_sector": {k: _agg(v) for k, v in by_sector.items()},
        "by_exit_reason": {k: _agg(v) for k, v in by_exit.items()},
        "conviction_correlation": corr,
        "conviction_calibration": conviction_cal,
        "winners": winners,
        "losers": losers,
        "stopped_out": stopped_out,
        "audit_exits": audit_exits,
    }
