"""Authentication middleware — @require_auth, @require_broker, @require_admin decorators.

Usage:
    @bp.route("/some-endpoint", methods=["POST"])
    @require_auth
    def some_endpoint():
        user = g.current_user        # {"id": 1, "email": "...", "name": "...", "is_admin": False}
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
            "is_admin": bool(user.get("is_admin", False)),
            "onboarding_completed": bool(user.get("onboarding_completed", False)),
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


def require_admin(f):
    """Decorator that requires the current user to be an admin.
    Must be used AFTER @require_auth.

    Checks both the DB is_admin flag and the ADMIN_EMAIL env var as a fallback,
    so admin access works even if the DB promotion hasn't run yet.
    """
    import os

    @functools.wraps(f)
    def decorated(*args, **kwargs):
        user = getattr(g, "current_user", {})
        is_admin = bool(user.get("is_admin", False))

        # Fallback: check ADMIN_EMAIL env var directly against user's email
        if not is_admin:
            admin_email = os.getenv("ADMIN_EMAIL", "").strip().strip('"\'').lower()
            if admin_email and user.get("email", "").lower() == admin_email:
                is_admin = True

        if not is_admin:
            return jsonify({
                "success": False,
                "error": "Admin access required.",
                "code": "ADMIN_REQUIRED",
            }), 403

        return f(*args, **kwargs)

    return decorated


def require_tier(min_tier: int):
    """Decorator factory requiring user's derived tier >= min_tier.
    Must be used AFTER @require_auth.

    Usage:
        @require_auth
        @require_tier(2)
        def some_endpoint(): ...
    """

    def decorator(f):
        @functools.wraps(f)
        def decorated(*args, **kwargs):
            from services.tier_service import get_user_tier
            tier = get_user_tier(g.current_user["id"])
            if tier < min_tier:
                return jsonify({
                    "success": False,
                    "error": "Upgrade required to access this feature.",
                    "code": "TIER_INSUFFICIENT",
                    "current_tier": tier,
                    "required_tier": min_tier,
                }), 403
            return f(*args, **kwargs)
        return decorated

    return decorator
