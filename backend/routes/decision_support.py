"""Decision support endpoints — /api/decision-support/*"""

import logging

from flask import Blueprint, request, jsonify, Response, stream_with_context, g

from middleware.auth import require_auth, require_broker

logger = logging.getLogger(__name__)

decision_support_bp = Blueprint("decision_support", __name__, url_prefix="/api/decision-support")


@decision_support_bp.route("/run", methods=["POST"])
@require_auth
@require_broker
def run_decision_support():
    """SSE endpoint — runs the 4-2-1-1 stock selection pipeline."""
    try:
        from agents.decision_support.stream import run_decision_support_stream

        data = request.json or {}
        config = data.get("config", {})

        def generate():
            for event in run_decision_support_stream(g.broker_token, config=config):
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
@require_broker
def run_sell_analysis():
    """SSE endpoint — runs the portfolio sell analysis pipeline."""
    try:
        from agents.decision_support.sell_stream import run_sell_pipeline_stream

        data = request.json or {}
        config = data.get("config", {})

        def generate():
            for event in run_sell_pipeline_stream(g.broker_token, config=config):
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
