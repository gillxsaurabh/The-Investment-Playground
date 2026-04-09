"""Chat endpoints — /api/chat/*"""

import logging

from flask import Blueprint, request, jsonify, g

from extensions import limiter, get_user_or_ip
from middleware.auth import require_auth
from services.validation import validate_request, ChatSendBody

logger = logging.getLogger(__name__)

chat_bp = Blueprint("chat", __name__, url_prefix="/api/chat")


@chat_bp.route("/send", methods=["POST"])
@require_auth
@limiter.limit("10 per minute", key_func=get_user_or_ip)
@validate_request(ChatSendBody)
def chat_send(body: ChatSendBody):
    """Send message to LangGraph agent."""
    try:
        from agents import run_agent

        session_id = body.session_id or f"user_{g.current_user['id']}"
        access_token = getattr(g, "broker_token", "") or ""

        response_text = run_agent(
            message=body.message,
            session_id=session_id,
            access_token=access_token,
            user_id=g.current_user["id"],
        )

        return jsonify({
            "success": True,
            "response": response_text,
            "session_id": session_id,
        })

    except Exception as e:
        return jsonify({"success": False, "error": "Chat request failed"}), 500


@chat_bp.route("/clear", methods=["POST"])
@require_auth
def chat_clear():
    """Clear chat session."""
    try:
        from agents import clear_session

        data = request.json or {}
        session_id = data.get("session_id", f"user_{g.current_user['id']}")
        clear_session(session_id)

        return jsonify({"success": True, "message": "Chat session cleared"})

    except Exception as e:
        return jsonify({"success": False, "error": "Failed to clear session"}), 500
