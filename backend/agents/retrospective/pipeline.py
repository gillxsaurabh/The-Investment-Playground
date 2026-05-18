"""Retrospective pipeline orchestrator.

Runs 6 narrow Sonnet stages in parallel, then Opus synthesizer.
Returns a complete report dict ready for DB insertion.
"""

import json
import logging
import random
import string
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from typing import Any, Callable, Dict, Optional

from agents.retrospective.cohort_builder import build_cohorts
from agents.retrospective.stages import (
    run_winner_patterns,
    run_loser_patterns,
    run_filter_audit,
    run_sl_calibration,
    run_conviction_calibration,
    run_sell_audit_calibration,
    run_synthesizer,
)
from services.db import (
    get_closed_trades_for_retrospective,
    get_scan_rejection_stats,
    insert_retrospective_report,
)

logger = logging.getLogger(__name__)


def run_retrospective(
    trading_mode: str = "simulator",
    lookback_days: int = 90,
    triggered_by: str = "manual",
    user_id: Optional[int] = None,
    progress_cb: Optional[Callable[[str, str], None]] = None,
) -> Dict[str, Any]:
    """Run the full retrospective pipeline and persist the report.

    Args:
        trading_mode: 'simulator' or 'live'
        lookback_days: how far back to look for closed trades
        triggered_by: 'manual' or 'monthly_cron'
        user_id: admin user who triggered this
        progress_cb: optional callback(stage_name, message) for SSE streaming

    Returns the persisted report dict.
    """
    def _emit(stage: str, msg: str):
        if progress_cb:
            progress_cb(stage, msg)
        logger.info("[Retrospective][%s] %s", stage, msg)

    now = datetime.utcnow()
    period_end = now.strftime("%Y-%m-%d %H:%M:%S")
    period_start = (now - timedelta(days=lookback_days)).strftime("%Y-%m-%d %H:%M:%S")

    rand_s = "".join(random.choices(string.ascii_lowercase + string.digits, k=6))
    report_id = f"RETRO_{now.strftime('%Y%m%d_%H%M%S')}_{rand_s}"

    _emit("pipeline", f"Starting retrospective analysis — mode={trading_mode}, lookback={lookback_days}d")

    # ── Data fetch ────────────────────────────────────────────────────────
    _emit("data_fetch", "Fetching closed trades from database...")
    trades = get_closed_trades_for_retrospective(trading_mode, period_start, period_end)
    _emit("data_fetch", f"Loaded {len(trades)} closed trades")

    rejection_stats = get_scan_rejection_stats(period_start, period_end)
    _emit("data_fetch", f"Loaded {len(rejection_stats)} scan candidate records")

    if not trades:
        _emit("pipeline", "No closed trades in period — skipping LLM stages")
        report = {
            "report_id": report_id,
            "generated_at": now.isoformat(sep=" ", timespec="seconds"),
            "trading_mode": trading_mode,
            "period_start": period_start,
            "period_end": period_end,
            "lookback_days": lookback_days,
            "trades_analyzed": 0,
            "winners": 0,
            "losers": 0,
            "claude_findings": "No closed trades in this period to analyze.",
            "claude_recommendations": [],
            "triggered_by": triggered_by,
            "user_id": user_id,
        }
        insert_retrospective_report(report)
        return report

    # ── Stage 1: Cohort Builder (deterministic) ───────────────────────────
    _emit("cohort_builder", "Building cohorts and computing aggregates...")
    cohorts = build_cohorts(trades)
    summary = cohorts["summary"]
    _emit("cohort_builder", f"Cohorts built: {summary['winners']} winners, {summary['losers']} losers, {summary['win_rate_pct']}% win rate")

    # ── Stages 2-6b in parallel ───────────────────────────────────────────
    stage_results: Dict[str, Dict] = {}

    def _run_stage(name: str, fn, *args):
        _emit(name, "Running...")
        try:
            result = fn(*args, user_id=user_id)
            _emit(name, "Complete")
            return name, result
        except Exception as e:
            logger.warning("[Retrospective][%s] Stage failed: %s", name, e)
            _emit(name, f"Failed: {e}")
            return name, {"error": str(e)}

    with ThreadPoolExecutor(max_workers=6) as executor:
        futures = [
            executor.submit(_run_stage, "winner_patterns",
                            run_winner_patterns, cohorts["winners"], summary),
            executor.submit(_run_stage, "loser_patterns",
                            run_loser_patterns, cohorts["losers"], cohorts["stopped_out"], summary),
            executor.submit(_run_stage, "filter_audit",
                            run_filter_audit, rejection_stats, summary),
            executor.submit(_run_stage, "sl_calibration",
                            run_sl_calibration, cohorts["stopped_out"], summary),
            executor.submit(_run_stage, "conviction_calibration",
                            run_conviction_calibration,
                            cohorts["conviction_calibration"],
                            cohorts.get("conviction_correlation"),
                            cohorts),
            executor.submit(_run_stage, "sell_audit_calibration",
                            run_sell_audit_calibration, cohorts["audit_exits"], summary),
        ]
        for future in as_completed(futures):
            name, result = future.result()
            stage_results[name] = result

    # ── Stage 7: Synthesizer (Opus 4.7 + extended thinking) ──────────────
    _emit("synthesizer", "Synthesizing findings with Opus 4.7 (extended thinking)...")

    # Build cohort aggregates for synthesizer (exclude raw trade lists to keep context tight)
    cohort_agg_for_synth = {k: v for k, v in cohorts.items()
                            if k not in ("winners", "losers", "stopped_out", "audit_exits", "conviction_calibration")}

    synthesis = run_synthesizer(
        cohort_aggregates=cohort_agg_for_synth,
        winner_patterns=stage_results.get("winner_patterns", {}),
        loser_patterns=stage_results.get("loser_patterns", {}),
        filter_audit=stage_results.get("filter_audit", {}),
        sl_calibration=stage_results.get("sl_calibration", {}),
        conviction_cal=stage_results.get("conviction_calibration", {}),
        sell_audit_cal=stage_results.get("sell_audit_calibration", {}),
        user_id=user_id,
    )
    _emit("synthesizer", f"Synthesis complete — {len(synthesis.get('recommendations', []))} recommendations generated")

    # ── Assemble + persist report ─────────────────────────────────────────
    wins_count = summary["winners"]
    losses_count = summary["losers"]
    trades_count = summary["trades"]
    report = {
        "report_id": report_id,
        "generated_at": now.isoformat(sep=" ", timespec="seconds"),
        "trading_mode": trading_mode,
        "period_start": period_start,
        "period_end": period_end,
        "lookback_days": lookback_days,
        "trades_analyzed": trades_count,
        "winners": wins_count,
        "losers": losses_count,
        "win_rate_pct": summary.get("win_rate_pct"),
        "total_pnl": summary.get("total_pnl_pct"),
        "avg_pnl_pct": summary.get("avg_pnl_pct"),
        "cohort_aggregates": cohort_agg_for_synth,
        "winner_patterns": stage_results.get("winner_patterns", {}),
        "loser_patterns": stage_results.get("loser_patterns", {}),
        "filter_audit": stage_results.get("filter_audit", {}),
        "sl_calibration": stage_results.get("sl_calibration", {}),
        "conviction_cal": stage_results.get("conviction_calibration", {}),
        "sell_audit_cal": stage_results.get("sell_audit_calibration", {}),
        "claude_findings": synthesis.get("findings_markdown", ""),
        "claude_recommendations": synthesis.get("recommendations", []),
        "triggered_by": triggered_by,
        "user_id": user_id,
    }

    insert_retrospective_report(report)
    _emit("pipeline", f"Report {report_id} saved to database")
    return report
