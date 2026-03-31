"""Admin endpoints — /api/admin/*

Admin-only operations: global broker token management, system stats.
"""

import logging
import os

from flask import Blueprint, jsonify, g

from broker.kite_adapter import KiteBrokerAdapter
from middleware.auth import require_auth, require_admin
from services.validation import validate_request, BrokerLinkBody
from services.admin_token_service import (
    get_admin_broker_token,
    set_admin_broker_token,
    is_admin_token_valid,
)

logger = logging.getLogger(__name__)

admin_bp = Blueprint("admin", __name__, url_prefix="/api/admin")


@admin_bp.route("/whoami", methods=["GET"])
@require_auth
def whoami():
    """Diagnostic endpoint — shows whether current user is seen as admin. No admin required."""
    user = g.current_user
    admin_email_raw = os.getenv("ADMIN_EMAIL", "")
    admin_email = admin_email_raw.strip().strip('"\'').lower()
    user_email = user.get("email", "").lower()
    return jsonify({
        "user_email": user_email,
        "is_admin_db": bool(user.get("is_admin", False)),
        "admin_email_env_set": bool(admin_email),
        "admin_email_first3": admin_email[:3] if admin_email else "",
        "admin_email_domain": admin_email.split("@")[1] if "@" in admin_email else "",
        "emails_match": user_email == admin_email,
        "admin_email_raw_length": len(admin_email_raw),
    })


@admin_bp.route("/bootstrap", methods=["POST"])
@require_auth
def bootstrap_admin():
    """One-time endpoint to promote current user to admin.
    Only works when NO admin users exist yet — self-disables after first use.
    """
    from services.db import get_conn
    conn = get_conn()
    try:
        existing = conn.execute(
            "SELECT id FROM users WHERE is_admin = TRUE LIMIT 1"
        ).fetchone()
        if existing:
            return jsonify({"success": False, "error": "An admin already exists. Bootstrap is disabled."}), 403

        user_id = g.current_user["id"]
        conn.execute("UPDATE users SET is_admin = TRUE WHERE id = ?", (user_id,))
        conn.commit()
        logger.info("[Admin] Bootstrapped admin for user_id=%s via /bootstrap endpoint", user_id)
        return jsonify({"success": True, "message": "You are now admin. Refresh the page."})
    finally:
        conn.close()


@admin_bp.route("/broker/login-url", methods=["GET"])
@require_auth
@require_admin
def admin_broker_login_url():
    """Get Zerodha login URL for admin broker token."""
    try:
        broker = KiteBrokerAdapter()
        login_url = broker.login_url()
        return jsonify({"success": True, "login_url": login_url})
    except Exception:
        logger.exception("[Admin] Failed to get broker login URL")
        return jsonify({"success": False, "error": "Failed to get login URL"}), 500


@admin_bp.route("/broker/link", methods=["POST"])
@require_auth
@require_admin
@validate_request(BrokerLinkBody)
def admin_broker_link(body: BrokerLinkBody):
    """Exchange Kite request_token and store as global admin broker token."""
    try:
        broker = KiteBrokerAdapter()
        session_data = broker.generate_session(body.request_token)
        access_token = session_data["access_token"]

        broker.set_access_token(access_token)
        profile = broker.profile()

        set_admin_broker_token(
            user_id=g.current_user["id"],
            access_token=access_token,
        )

        return jsonify({
            "success": True,
            "message": "Admin broker token linked successfully",
            "broker": {
                "broker_user_id": profile.get("user_id"),
                "broker_user_name": profile.get("user_name"),
            },
        })
    except Exception:
        logger.exception("[Admin] Broker linking failed")
        return jsonify({"success": False, "error": "Failed to link admin broker"}), 500


@admin_bp.route("/broker/status", methods=["GET"])
@require_auth
@require_admin
def admin_broker_status():
    """Check if admin broker token is active and valid."""
    token = get_admin_broker_token()
    if not token:
        return jsonify({"success": True, "active": False, "valid": False})

    valid = is_admin_token_valid()
    return jsonify({"success": True, "active": True, "valid": valid})


@admin_bp.route("/dashboard", methods=["GET"])
@require_auth
@require_admin
def admin_dashboard():
    """System stats: user count by tier, admin token status."""
    from services.db import get_conn
    from services.tier_service import get_user_tier, TIER_NAMES

    conn = get_conn()
    try:
        users = conn.execute(
            "SELECT id FROM users WHERE is_active = TRUE"
        ).fetchall()
        total_users = len(users)

        tier_counts = {1: 0, 2: 0, 3: 0}
        for row in users:
            tier = get_user_tier(row["id"])
            tier_counts[tier] = tier_counts.get(tier, 0) + 1

        token_active = get_admin_broker_token() is not None
        token_valid = is_admin_token_valid() if token_active else False

        return jsonify({
            "success": True,
            "total_users": total_users,
            "tiers": {
                TIER_NAMES[k]: v for k, v in tier_counts.items()
            },
            "admin_broker": {
                "active": token_active,
                "valid": token_valid,
            },
        })
    finally:
        conn.close()
