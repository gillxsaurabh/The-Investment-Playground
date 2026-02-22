"""Chat endpoints — /api/chat/*"""

import logging

from flask import Blueprint, request, jsonify

logger = logging.getLogger(__name__)

chat_bp = Blueprint("chat", __name__, url_prefix="/api/chat")


@chat_bp.route("/send", methods=["POST"])
def chat_send():
    """Send message to LangGraph agent."""
    try:
        from agents import run_agent

        data = request.json
        message = data.get("message", "")
        session_id = data.get("session_id", "default")
        access_token = data.get("access_token", "")

        if not message:
            return jsonify({"success": False, "error": "Message is required"}), 400

        response_text = run_agent(
            message=message,
            session_id=session_id,
            access_token=access_token,
        )

        return jsonify(
            {"success": True, "response": response_text, "session_id": session_id}
        )

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@chat_bp.route("/clear", methods=["POST"])
def chat_clear():
    """Clear chat session."""
    try:
        from agents import clear_session

        data = request.json
        session_id = data.get("session_id", "default")
        clear_session(session_id)

        return jsonify({"success": True, "message": "Chat session cleared"})

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500
