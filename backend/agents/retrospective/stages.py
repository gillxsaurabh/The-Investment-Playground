"""Retrospective analysis stages 2-7.

Each stage is a focused LLM call with a narrow context:
  Stage 2: Winner Pattern Hunter   — Sonnet 4.6
  Stage 3: Loser Pattern Hunter    — Sonnet 4.6
  Stage 4: Filter Rejection Auditor— Sonnet 4.6
  Stage 5: Stop-Loss Calibrator    — Sonnet 4.6
  Stage 6: Conviction Calibrator   — Sonnet 4.6
  Stage 6b: Sell-Audit Calibrator  — Sonnet 4.6
  Stage 7: Synthesizer             — Opus 4.7 + extended_thinking

All LLM calls request structured JSON output.
"""

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from agents.config import get_llm

logger = logging.getLogger(__name__)

_PARAM_INVENTORY_PATH = Path(__file__).parent.parent.parent.parent / "admin_panel_inventory.md"

_SYSTEM_BASE = (
    "You are a quantitative trading system analyst reviewing the historical performance "
    "of CogniCap — an automated stock discovery and paper-trading system that runs on the NSE "
    "(India). Your job is to identify patterns in the outcome data and produce specific, "
    "actionable recommendations for improving the system's parameters and filters.\n\n"
    "Always respond with valid JSON only — no markdown fences, no prose outside the JSON structure."
)


def _call_llm(prompt: str, user_id: Optional[int], stage_name: str) -> Dict[str, Any]:
    """Call Sonnet 4.6 and parse JSON response."""
    try:
        llm = get_llm(
            provider="claude",
            temperature=0.1,
            user_id=user_id,
            pipeline="retrospective",
        )
        response = llm.invoke([
            {"role": "system", "content": _SYSTEM_BASE},
            {"role": "user", "content": prompt},
        ])
        text = response.content.strip()
        if text.startswith("```"):
            parts = text.split("```")
            text = parts[1].lstrip("json").strip() if len(parts) > 1 else text
        return json.loads(text)
    except json.JSONDecodeError as e:
        logger.warning("[Retrospective][%s] JSON parse error: %s", stage_name, e)
        return {"error": f"JSON parse error: {e}", "raw": text[:500] if "text" in dir() else ""}
    except Exception as e:
        logger.warning("[Retrospective][%s] LLM call failed: %s", stage_name, e)
        return {"error": str(e)}


def run_winner_patterns(winners: List[Dict], cohort_summary: Dict, user_id: Optional[int]) -> Dict:
    """Stage 2 — identify what winning trades had in common."""
    if not winners:
        return {"patterns": [], "cited_trades": [], "note": "No winners in period"}

    trades_json = json.dumps([{
        "trade_id": t.get("trade_id"),
        "symbol": t.get("symbol"),
        "sector": t.get("sector"),
        "gear": t.get("gear_at_entry"),
        "pnl_pct": t.get("realized_pnl_pct"),
        "holding_days": t.get("holding_days"),
        "exit_reason": t.get("exit_reason"),
        "scan_ai_conviction": t.get("scan_ai_conviction"),
        "scan_composite_score": t.get("scan_composite_score"),
        "scan_rsi": t.get("scan_rsi"),
        "scan_adx": t.get("scan_adx"),
        "scan_rsi_trigger": t.get("scan_rsi_trigger"),
        "why_selected": t.get("why_selected"),
        "rank_reason": t.get("rank_reason"),
    } for t in winners], indent=2)

    prompt = f"""Analyze these {len(winners)} winning trades (>2% return) from CogniCap's paper trading simulator.

OVERALL STATS: {json.dumps(cohort_summary)}

WINNING TRADES:
{trades_json}

Find 3-5 specific patterns that distinguish winners. Avoid stating the obvious (e.g. "they had high scores") —
look for non-obvious commonalities: sector clusters, gear combinations, RSI trigger types, conviction thresholds
that correlate with higher returns, holding duration patterns, etc.

Respond with JSON:
{{
  "patterns": [
    {{
      "pattern": "short description",
      "detail": "2-3 sentence explanation with specifics",
      "cited_trades": ["trade_id1", "trade_id2"],
      "confidence": "high|medium|low"
    }}
  ],
  "top_gear_for_winners": "gear number and why",
  "optimal_conviction_threshold": "minimum conviction that predicts wins based on data"
}}"""

    return _call_llm(prompt, user_id, "winner_patterns")


def run_loser_patterns(losers: List[Dict], stopped_out: List[Dict], cohort_summary: Dict, user_id: Optional[int]) -> Dict:
    """Stage 3 — identify what losing trades had in common, was it discovery or exit failure."""
    if not losers and not stopped_out:
        return {"patterns": [], "note": "No losers in period"}

    all_losers = {t.get("trade_id"): t for t in losers + stopped_out}.values()
    trades_json = json.dumps([{
        "trade_id": t.get("trade_id"),
        "symbol": t.get("symbol"),
        "sector": t.get("sector"),
        "gear": t.get("gear_at_entry"),
        "pnl_pct": t.get("realized_pnl_pct"),
        "holding_days": t.get("holding_days"),
        "exit_reason": t.get("exit_reason"),
        "scan_ai_conviction": t.get("scan_ai_conviction"),
        "scan_composite_score": t.get("scan_composite_score"),
        "scan_rsi": t.get("scan_rsi"),
        "scan_adx": t.get("scan_adx"),
        "scan_rsi_trigger": t.get("scan_rsi_trigger"),
        "exit_urgency_level": t.get("exit_urgency_level"),
        "exit_urgency_reasons": t.get("exit_urgency_reasons"),
        "why_selected": t.get("why_selected"),
    } for t in all_losers], indent=2)

    prompt = f"""Analyze these {len(list(all_losers))} losing/stopped-out trades from CogniCap's paper trading simulator.

OVERALL STATS: {json.dumps(cohort_summary)}

LOSING TRADES:
{trades_json}

For each pattern, determine: was the failure in DISCOVERY (wrong stock selected) or EXIT (stop too tight / held too long)?

Respond with JSON:
{{
  "patterns": [
    {{
      "pattern": "short description",
      "failure_type": "discovery|exit|both",
      "detail": "2-3 sentence explanation with specifics",
      "cited_trades": ["trade_id1"],
      "confidence": "high|medium|low"
    }}
  ],
  "primary_failure_mode": "discovery|exit|both — which is more prevalent",
  "discovery_failure_note": "what specifically went wrong at the selection stage",
  "exit_failure_note": "what specifically went wrong at the exit stage"
}}"""

    return _call_llm(prompt, user_id, "loser_patterns")


def run_filter_audit(rejection_stats: List[Dict], cohort_summary: Dict, user_id: Optional[int]) -> Dict:
    """Stage 4 — which filter stage is too tight or too loose."""
    if not rejection_stats:
        return {"findings": [], "note": "No scan candidate data available yet"}

    from collections import Counter
    universe_rejects = Counter(r.get("universe_fail_reason") for r in rejection_stats if not r.get("passed_universe_filter") and r.get("universe_fail_reason"))
    tech_rejects = Counter(r.get("technical_fail_reason") for r in rejection_stats if not r.get("passed_technical_filter") and r.get("technical_fail_reason"))
    fund_rejects = Counter(r.get("fundamental_fail_reason") for r in rejection_stats if not r.get("passed_fundamental_filter") and r.get("fundamental_fail_reason"))
    sector_rejects = Counter(r.get("sector_fail_reason") for r in rejection_stats if not r.get("passed_sector_filter") and r.get("sector_fail_reason"))

    total = len(rejection_stats)
    passed_universe = sum(1 for r in rejection_stats if r.get("passed_universe_filter"))
    passed_tech = sum(1 for r in rejection_stats if r.get("passed_technical_filter"))
    passed_fund = sum(1 for r in rejection_stats if r.get("passed_fundamental_filter"))
    passed_sector = sum(1 for r in rejection_stats if r.get("passed_sector_filter"))
    reached_shortlist = sum(1 for r in rejection_stats if r.get("reached_final_shortlist"))

    funnel_data = {
        "total_evaluated": total,
        "passed_universe": passed_universe,
        "passed_technical": passed_tech,
        "passed_fundamental": passed_fund,
        "passed_sector": passed_sector,
        "reached_shortlist": reached_shortlist,
        "universe_reject_reasons": dict(universe_rejects.most_common(5)),
        "technical_reject_reasons": dict(tech_rejects.most_common(5)),
        "fundamental_reject_reasons": dict(fund_rejects.most_common(5)),
        "sector_reject_reasons": dict(sector_rejects.most_common(5)),
    }

    prompt = f"""Analyze this filter funnel data from CogniCap's stock discovery pipeline.

FUNNEL DATA: {json.dumps(funnel_data, indent=2)}
TRADE OUTCOMES: {json.dumps(cohort_summary)}

Identify which filter stages appear too aggressive (dropping too many stocks) or too lenient
(passing stocks that became losers). Look at the rejection reason distributions.

Respond with JSON:
{{
  "findings": [
    {{
      "stage": "universe_filter|technical_filter|fundamental_filter|sector_filter",
      "verdict": "too_tight|too_loose|well_calibrated",
      "detail": "2-3 sentences with specifics",
      "suggested_adjustment": "concrete change, e.g. relax ema_period from 200 to 150"
    }}
  ],
  "most_aggressive_stage": "stage name",
  "most_lenient_stage": "stage name"
}}"""

    return _call_llm(prompt, user_id, "filter_audit")


def run_sl_calibration(stopped_out: List[Dict], cohort_summary: Dict, user_id: Optional[int]) -> Dict:
    """Stage 5 — was the trailing stop multiplier right by gear."""
    if not stopped_out:
        return {"findings": [], "note": "No trailing-stop exits to analyze"}

    from collections import defaultdict
    by_gear: Dict[str, List] = defaultdict(list)
    for t in stopped_out:
        gear = str(t.get("gear_at_entry") or "unknown")
        by_gear[gear].append({
            "trade_id": t.get("trade_id"),
            "symbol": t.get("symbol"),
            "entry_price": t.get("entry_price"),
            "exit_price": t.get("exit_price"),
            "initial_sl": t.get("initial_sl"),
            "atr_at_entry": t.get("atr_at_entry"),
            "trail_multiplier": t.get("trail_multiplier"),
            "pnl_pct": t.get("realized_pnl_pct"),
            "holding_days": t.get("holding_days"),
            "scan_rsi_trigger": t.get("scan_rsi_trigger"),
            "risk_per_share": t.get("risk_per_share"),
        })

    # Compute stop-distance % for each stopped trade
    for gear_trades in by_gear.values():
        for t in gear_trades:
            if t["entry_price"] and t["initial_sl"]:
                t["sl_distance_pct"] = round(
                    (t["entry_price"] - t["initial_sl"]) / t["entry_price"] * 100, 2
                )

    prompt = f"""Analyze these trailing-stop exits from CogniCap's paper trading simulator.

STOPPED-OUT TRADES BY GEAR:
{json.dumps(dict(by_gear), indent=2)}

OVERALL STATS: {json.dumps(cohort_summary)}

For each gear, assess whether the ATR stop-loss multiplier appears too tight (stops being hit
on normal noise before the trend plays out) or too loose (giving back too much profit).
Consider the pnl_pct at stop and the sl_distance_pct.

Respond with JSON:
{{
  "findings": [
    {{
      "gear": "1|2|3|4|5",
      "current_multiplier": 1.5,
      "verdict": "too_tight|too_loose|appropriate",
      "detail": "specific evidence from the trades",
      "suggested_multiplier": 1.75,
      "cited_trades": ["trade_id1"]
    }}
  ],
  "overall_sl_verdict": "summary across all gears"
}}"""

    return _call_llm(prompt, user_id, "sl_calibration")


def run_conviction_calibration(conviction_calibration: List[Dict], conviction_corr: Optional[float], cohort_summary: Dict, user_id: Optional[int]) -> Dict:
    """Stage 6 — is the AI conviction score predictive of returns."""
    if not conviction_calibration:
        return {"findings": "No conviction data available", "note": "No scan_id linked to trades yet"}

    prompt = f"""Analyze whether CogniCap's AI conviction score (1-10) is predictive of trade returns.

CONVICTION vs RETURN PAIRS (conviction, pnl_pct):
{json.dumps(conviction_calibration, indent=2)}

PEARSON CORRELATION (conviction vs return): {conviction_corr}

COHORT AGGREGATES BY CONVICTION TIER: {json.dumps(cohort_summary.get("by_conviction", {}), indent=2)}

Assess: Is the conviction score a useful signal? Is the threshold for "high conviction"
set appropriately? Should the weight of conviction in final ranking be increased or decreased?

Respond with JSON:
{{
  "is_predictive": true,
  "correlation_interpretation": "strong|moderate|weak|inverse",
  "detail": "2-3 sentences interpreting the correlation and tier aggregates",
  "optimal_min_conviction": 7,
  "weight_recommendation": "increase|decrease|maintain",
  "weight_reasoning": "specific evidence"
}}"""

    return _call_llm(prompt, user_id, "conviction_calibration")


def run_sell_audit_calibration(audit_exits: List[Dict], cohort_summary: Dict, user_id: Optional[int]) -> Dict:
    """Stage 6b — did sell audits correctly identify exits."""
    if not audit_exits:
        return {"findings": "No audit-linked exits yet", "note": "No exit_audit_id linked to closed trades"}

    trades_json = json.dumps([{
        "trade_id": t.get("trade_id"),
        "symbol": t.get("symbol"),
        "exit_urgency_level": t.get("exit_urgency_level"),
        "exit_urgency_reasons": t.get("exit_urgency_reasons"),
        "exit_ai_reasoning": t.get("exit_ai_reasoning"),
        "pnl_pct": t.get("realized_pnl_pct"),
        "holding_days": t.get("holding_days"),
        "exit_reason": t.get("exit_reason"),
    } for t in audit_exits], indent=2)

    prompt = f"""Analyze trades that were exited after a sell audit recommendation.

AUDIT-DRIVEN EXITS:
{trades_json}

Assess: Did STRONG SELL and SELL recommendations lead to beneficial exits (avoided losses /
locked in gains)? Were any audits premature (stock would have recovered if held)?

Respond with JSON:
{{
  "strong_sell_accuracy": "high|medium|low",
  "sell_accuracy": "high|medium|low",
  "premature_exits_detected": true,
  "detail": "2-3 sentences with specific evidence",
  "threshold_recommendation": "raise_urgency_threshold|lower_threshold|maintain",
  "reasoning": "specific evidence from the trade outcomes"
}}"""

    return _call_llm(prompt, user_id, "sell_audit_calibration")


def run_synthesizer(
    cohort_aggregates: Dict,
    winner_patterns: Dict,
    loser_patterns: Dict,
    filter_audit: Dict,
    sl_calibration: Dict,
    conviction_cal: Dict,
    sell_audit_cal: Dict,
    user_id: Optional[int],
) -> Dict:
    """Stage 7 — Opus 4.7 with extended thinking synthesizes all findings into ranked recommendations."""

    # Load param inventory for context (truncate to avoid token overload)
    param_inventory = ""
    if _PARAM_INVENTORY_PATH.exists():
        raw = _PARAM_INVENTORY_PATH.read_text()
        # Include full doc — it's the reference for which parameters exist
        param_inventory = raw[:15000]  # ~4k tokens

    stage_outputs = {
        "cohort_aggregates_summary": cohort_aggregates.get("summary", {}),
        "by_gear": cohort_aggregates.get("by_gear", {}),
        "by_conviction": cohort_aggregates.get("by_conviction", {}),
        "by_rsi_trigger": cohort_aggregates.get("by_rsi_trigger", {}),
        "winner_patterns": winner_patterns,
        "loser_patterns": loser_patterns,
        "filter_audit": filter_audit,
        "sl_calibration": sl_calibration,
        "conviction_calibration": conviction_cal,
        "sell_audit_calibration": sell_audit_cal,
    }

    prompt = f"""You are synthesizing a retrospective analysis of CogniCap's automated stock trading system.

## Stage Outputs from 6 specialist analysts:
{json.dumps(stage_outputs, indent=2)}

## CogniCap Parameter Inventory (what can be tuned):
{param_inventory}

## Your task:
1. Write a concise markdown narrative (3-5 paragraphs) summarizing the key findings.
2. Produce a ranked list of specific parameter recommendations ordered by expected impact.

For each recommendation, cite which stages supported it and which trade_ids are evidence.
Be specific — say "raise rsi_buy_limit from 30 to 38 for Gear 2" not "consider adjusting RSI thresholds".
If data is too sparse for a confident recommendation, say so and set confidence to "low".

Respond with JSON:
{{
  "findings_markdown": "## Retrospective Analysis\\n\\n...",
  "recommendations": [
    {{
      "rank": 1,
      "parameter": "exact parameter name from inventory",
      "file": "backend/... file path",
      "current_value": "current value",
      "suggested_value": "suggested new value",
      "reasoning": "2-3 sentence evidence-based justification",
      "confidence": "high|medium|low",
      "expected_impact": "brief description of expected improvement",
      "supporting_stages": ["winner_patterns", "loser_patterns"],
      "cited_trades": ["trade_id1", "trade_id2"]
    }}
  ]
}}"""

    try:
        llm = get_llm(
            provider="claude",
            model_override="claude-opus-4-7",
            extended_thinking=True,
            thinking_budget=8000,
            user_id=user_id,
            pipeline="retrospective",
        )
        response = llm.invoke([
            {"role": "system", "content": _SYSTEM_BASE},
            {"role": "user", "content": prompt},
        ])
        text = response.content.strip()
        if text.startswith("```"):
            parts = text.split("```")
            text = parts[1].lstrip("json").strip() if len(parts) > 1 else text
        return json.loads(text)
    except json.JSONDecodeError as e:
        logger.warning("[Retrospective][synthesizer] JSON parse error: %s", e)
        return {"findings_markdown": "Synthesis failed — JSON parse error.", "recommendations": []}
    except Exception as e:
        logger.warning("[Retrospective][synthesizer] LLM call failed: %s", e)
        return {"findings_markdown": f"Synthesis failed: {e}", "recommendations": []}
