"""Authentication endpoints — /api/auth/*"""

import json
import logging
from datetime import datetime
from pathlib import Path

from flask import Blueprint, request, jsonify

from broker import get_broker
from broker.kite_adapter import KiteBrokerAdapter
from config import TOKEN_FILE

logger = logging.getLogger(__name__)

auth_bp = Blueprint("auth", __name__, url_prefix="/api/auth")


@auth_bp.route("/login-url", methods=["GET"])
def get_login_url():
    """Get Zerodha login URL."""
    try:
        broker = KiteBrokerAdapter()
        login_url = broker.login_url()
        return jsonify({"success": True, "login_url": login_url})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@auth_bp.route("/authenticate", methods=["POST"])
def authenticate():
    """Authenticate with request token."""
    try:
        data = request.json
        request_token = data.get("request_token")

        if not request_token:
            return jsonify({"success": False, "error": "Request token is required"}), 400

        broker = KiteBrokerAdapter()
        session_data = broker.generate_session(request_token)
        access_token = session_data["access_token"]

        # Save token
        token_path = Path(TOKEN_FILE)
        token_path.parent.mkdir(parents=True, exist_ok=True)
        with open(token_path, "w") as f:
            json.dump(
                {
                    "access_token": access_token,
                    "date": datetime.now().strftime("%Y-%m-%d"),
                    "timestamp": datetime.now().isoformat(),
                },
                f,
                indent=2,
            )

        broker.set_access_token(access_token)
        profile = broker.profile()

        return jsonify(
            {
                "success": True,
                "access_token": access_token,
                "user": {
                    "name": profile["user_name"],
                    "email": profile["email"],
                    "user_id": profile["user_id"],
                },
            }
        )

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@auth_bp.route("/verify", methods=["POST"])
def verify_token():
    """Verify if token is valid."""
    try:
        data = request.json
        access_token = data.get("access_token")

        if not access_token:
            return jsonify({"success": False, "error": "Access token is required"}), 400

        broker = get_broker(access_token)
        profile = broker.profile()

        return jsonify(
            {
                "success": True,
                "user": {
                    "name": profile["user_name"],
                    "email": profile["email"],
                    "user_id": profile["user_id"],
                },
            }
        )

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 401
