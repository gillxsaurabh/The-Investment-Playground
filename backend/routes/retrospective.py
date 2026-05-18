"""Retrospective analysis routes — /api/retrospective/*

Admin-only. All endpoints require @require_admin.
"""

import json
import logging

from flask import Blueprint, Response, jsonify, request, stream_with_context, g

from middleware.auth import require_auth, require_admin

logger = logging.getLogger(__name__)

retrospective_bp = Blueprint("retrospective", __name__, url_prefix="/api/retrospective")


@retrospective_bp.route("/run", methods=["POST"])
@require_auth
@require_admin
def retrospective_run():
    """SSE endpoint — streams the retrospective pipeline and returns a report."""
    data = request.get_json(silent=True) or {}
    trading_mode = data.get("trading_mode", "simulator")
    lookback_days = int(data.get("lookback_days", 90))
    user_id = g.current_user["id"]

    if trading_mode not in ("simulator", "live", "all"):
        return jsonify({"error": "trading_mode must be simulator | live | all"}), 400
    if not (7 <= lookback_days <= 365):
        return jsonify({"error": "lookback_days must be between 7 and 365"}), 400

    def generate():
        from agents.retrospective.stream import run_retrospective_stream
        for event in run_retrospective_stream(
            trading_mode=trading_mode,
            lookback_days=lookback_days,
            triggered_by="manual",
            user_id=user_id,
        ):
            yield event
        yield "event: end\ndata: {}\n\n"

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


@retrospective_bp.route("/reports", methods=["GET"])
@require_auth
@require_admin
def list_reports():
    """List past retrospective reports."""
    from services.db import list_retrospective_reports
    trading_mode = request.args.get("mode")
    limit = min(int(request.args.get("limit", 20)), 50)
    reports = list_retrospective_reports(trading_mode=trading_mode, limit=limit)
    # Deserialize JSON blobs for the list view (omit heavy fields)
    slim = []
    for r in reports:
        slim.append({
            "report_id": r["report_id"],
            "generated_at": r["generated_at"],
            "trading_mode": r["trading_mode"],
            "period_start": r["period_start"],
            "period_end": r["period_end"],
            "lookback_days": r["lookback_days"],
            "trades_analyzed": r["trades_analyzed"],
            "winners": r["winners"],
            "losers": r["losers"],
            "win_rate_pct": r["win_rate_pct"],
            "total_pnl": r["total_pnl"],
            "avg_pnl_pct": r["avg_pnl_pct"],
            "triggered_by": r["triggered_by"],
            "recommendations_count": len(json.loads(r["claude_recommendations"] or "[]")),
        })
    return jsonify({"success": True, "reports": slim})


@retrospective_bp.route("/reports/<report_id>", methods=["GET"])
@require_auth
@require_admin
def get_report(report_id: str):
    """Fetch a full retrospective report by ID."""
    from services.db import get_retrospective_report
    report = get_retrospective_report(report_id)
    if not report:
        return jsonify({"error": "Report not found"}), 404

    # Deserialize all JSON blobs
    for key in ("cohort_aggregates", "winner_patterns", "loser_patterns",
                "filter_audit", "sl_calibration", "conviction_cal",
                "sell_audit_cal", "claude_recommendations"):
        if report.get(key) and isinstance(report[key], str):
            try:
                report[key] = json.loads(report[key])
            except Exception:
                pass

    return jsonify({"success": True, "report": report})
