"""Audit routes — unified Stock Audit pipeline.

Endpoints:
    POST /api/audit/run     — SSE streaming audit run
    GET  /api/audit/results — all cached audit results for current user
"""

import logging

from flask import Blueprint, Response, g, jsonify, request

from middleware.auth import require_auth, require_broker
from services.analysis_storage import get_all_audit_results

logger = logging.getLogger(__name__)

audit_bp = Blueprint("audit", __name__)


@audit_bp.route("/api/audit/run", methods=["POST"])
@require_auth
@require_broker
def run_audit():
    """Stream the unified Stock Audit pipeline as Server-Sent Events."""
    from agents.audit.audit_pipeline import run_stock_audit

    user_id      = g.current_user["id"]
    access_token = g.broker_token
    data         = request.get_json(silent=True) or {}
    llm_provider = data.get("llm_provider", "claude")

    def generate():
        try:
            yield from run_stock_audit(access_token, user_id, llm_provider)
        except Exception as e:
            import json
            logger.error("[Audit] Pipeline error for user=%s: %s", user_id, e, exc_info=True)
            yield f"event: error\ndata: {json.dumps({'message': str(e)})}\n\n"

    return Response(
        generate(),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@audit_bp.route("/api/audit/results", methods=["GET"])
@require_auth
def get_audit_results():
    """Return all cached audit results for the current user."""
    user_id = g.current_user["id"]
    results = get_all_audit_results(user_id)
    return jsonify({"success": True, "results": results, "total": len(results)})
