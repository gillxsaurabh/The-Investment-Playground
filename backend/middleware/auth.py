"""Authentication middleware — @require_auth decorator for Flask routes.

Usage:
    @bp.route("/some-endpoint", methods=["POST"])
    @require_auth
    def some_endpoint():
        user = g.current_user        # {"id": 1, "email": "...", "name": "..."}
        broker_token = g.broker_token # Kite access token or None
        ...
"""

import functools
import logging

from flask import request, jsonify, g

from services.auth_service import decode_access_token, get_user_by_id, get_broker_token

logger = logging.getLogger(__name__)


def require_auth(f):
    """Decorator that validates JWT Bearer token and populates g.current_user."""

    @functools.wraps(f)
    def decorated(*args, **kwargs):
        auth_header = request.headers.get("Authorization", "")

        if not auth_header.startswith("Bearer "):
            return jsonify({"success": False, "error": "Missing or invalid Authorization header"}), 401

        token = auth_header[7:]  # strip "Bearer "
        payload = decode_access_token(token)

        if payload is None:
            return jsonify({"success": False, "error": "Invalid or expired token"}), 401

        user_id = payload.get("sub")
        user = get_user_by_id(user_id)

        if not user or not user.get("is_active"):
            return jsonify({"success": False, "error": "User not found or deactivated"}), 401

        # Populate Flask g context
        g.current_user = {
            "id": user["id"],
            "email": user["email"],
            "name": user["name"],
        }
        g.broker_token = get_broker_token(user["id"])

        return f(*args, **kwargs)

    return decorated


def require_broker(f):
    """Decorator that also ensures the user has a linked broker token.
    Must be used AFTER @require_auth.
    """

    @functools.wraps(f)
    def decorated(*args, **kwargs):
        if not getattr(g, "broker_token", None):
            return jsonify({
                "success": False,
                "error": "No broker account linked. Please link your Kite account first.",
                "code": "BROKER_NOT_LINKED",
            }), 403

        return f(*args, **kwargs)

    return decorated
