"""Decision support endpoints — /api/decision-support/*"""

import logging

from flask import Blueprint, request, jsonify, Response, stream_with_context, g

from middleware.auth import require_auth, require_broker
from extensions import limiter, get_user_or_ip

logger = logging.getLogger(__name__)

decision_support_bp = Blueprint("decision_support", __name__, url_prefix="/api/decision-support")


def _get_broker_token():
    """Return user's broker token, falling back to the admin token."""
    user_token = getattr(g, "broker_token", None)
    if user_token:
        return user_token
    from services.admin_token_service import get_admin_broker_token
    return get_admin_broker_token()


@decision_support_bp.route("/run", methods=["POST"])
@require_auth
@limiter.limit("3 per minute", key_func=get_user_or_ip)
def run_decision_support():
    """SSE endpoint — runs the 4-2-1-1 stock selection pipeline."""
    try:
        from agents.decision_support.stream import run_decision_support_stream

        data = request.json or {}
        config = data.get("config", {})

        user_id = g.current_user["id"]
        broker_token = _get_broker_token()
        if not broker_token:
            return jsonify({"success": False, "error": "No market data token available. Contact admin.", "code": "NO_MARKET_TOKEN"}), 503

        def generate():
            for event in run_decision_support_stream(broker_token, config=config, user_id=user_id):
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

    except Exception as e:
        return jsonify({"success": False, "error": "Pipeline failed"}), 500


@decision_support_bp.route("/sell", methods=["POST"])
@require_auth
@limiter.limit("3 per minute", key_func=get_user_or_ip)
@require_broker
def run_sell_analysis():
    """SSE endpoint — runs the portfolio sell analysis pipeline."""
    try:
        from agents.decision_support.sell_stream import run_sell_pipeline_stream

        data = request.json or {}
        config = data.get("config", {})

        user_id = g.current_user["id"]

        def generate():
            for event in run_sell_pipeline_stream(g.broker_token, config=config, user_id=user_id):
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

    except Exception as e:
        return jsonify({"success": False, "error": "Sell analysis failed"}), 500
