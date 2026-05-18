"""SSE streaming wrapper for the retrospective pipeline."""

import json
from agents.retrospective.pipeline import run_retrospective


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


def run_retrospective_stream(
    trading_mode: str = "simulator",
    lookback_days: int = 90,
    triggered_by: str = "manual",
    user_id=None,
):
    """Generator yielding SSE events as the retrospective pipeline runs."""
    yield _sse("step_start", {
        "step": "pipeline",
        "description": f"Starting retrospective analysis ({trading_mode}, {lookback_days}d lookback)...",
    })

    events: list[dict] = []

    def progress_cb(stage: str, message: str):
        events.append({"stage": stage, "message": message})

    # Run pipeline in same thread (streaming via collected events)
    # We yield events at the end of each major stage via the callback
    # For a true streaming feel we yield the captured events after the call
    # — the LLM stages are the slow part, so we emit a heartbeat first.

    STAGE_LABELS = {
        "pipeline": "Pipeline",
        "data_fetch": "Data Fetch",
        "cohort_builder": "Cohort Builder",
        "winner_patterns": "Winner Pattern Hunter",
        "loser_patterns": "Loser Pattern Hunter",
        "filter_audit": "Filter Rejection Auditor",
        "sl_calibration": "Stop-Loss Calibrator",
        "conviction_calibration": "Conviction Calibrator",
        "sell_audit_calibration": "Sell-Audit Calibrator",
        "synthesizer": "Synthesizer (Opus 4.7)",
    }

    completed_stages: set[str] = set()

    def streaming_cb(stage: str, message: str):
        events.append({"stage": stage, "message": message, "label": STAGE_LABELS.get(stage, stage)})

    try:
        report = run_retrospective(
            trading_mode=trading_mode,
            lookback_days=lookback_days,
            triggered_by=triggered_by,
            user_id=user_id,
            progress_cb=streaming_cb,
        )

        # Drain any buffered events first
        while events:
            ev = events.pop(0)
            stage = ev["stage"]
            if stage not in completed_stages and ev["message"] in ("Complete", "Running..."):
                if ev["message"] == "Complete":
                    completed_stages.add(stage)
                    yield _sse("step_complete", {"step": stage, "label": ev["label"]})
                else:
                    yield _sse("step_start", {"step": stage, "label": ev["label"], "description": f"{ev['label']} running..."})
            else:
                yield _sse("step_log", {"step": stage, "message": ev["message"]})

        yield _sse("final_result", {
            "report_id": report.get("report_id"),
            "trading_mode": trading_mode,
            "trades_analyzed": report.get("trades_analyzed", 0),
            "win_rate_pct": report.get("win_rate_pct"),
            "total_pnl": report.get("total_pnl"),
            "recommendations_count": len(report.get("claude_recommendations") or []),
            "findings_preview": (report.get("claude_findings") or "")[:500],
        })

    except Exception as e:
        yield _sse("error", {"message": str(e)})
