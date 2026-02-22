"""Decision support endpoints — /api/decision-support/*"""

import logging

from flask import Blueprint, request, jsonify, Response, stream_with_context

logger = logging.getLogger(__name__)

decision_support_bp = Blueprint("decision_support", __name__, url_prefix="/api/decision-support")


@decision_support_bp.route("/run", methods=["POST"])
def run_decision_support():
    """SSE endpoint — runs the 4-2-1-1 stock selection pipeline."""
    try:
        from agents.decision_support.stream import run_decision_support_stream

        data = request.json
        access_token = data.get("access_token")
        config = data.get("config", {})

        if not access_token:
            return jsonify({"success": False, "error": "access_token is required"}), 400

        def generate():
            for event in run_decision_support_stream(access_token, config=config):
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
        return jsonify({"success": False, "error": str(e)}), 500
