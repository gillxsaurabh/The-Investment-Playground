"""Authentication endpoints — /api/auth/*

Handles user registration, login, JWT refresh, profile, and broker linking.
"""

import logging

from flask import Blueprint, request, jsonify, g

from broker import get_broker
from broker.kite_adapter import KiteBrokerAdapter
from extensions import limiter
from middleware.auth import require_auth
from services.validation import (
    validate_request, RegisterBody, LoginBody, RefreshBody, BrokerLinkBody,
    ChangePasswordBody, ForgotPasswordBody, ResetPasswordBody, LLMKeyBody,
)
from services.auth_service import (
    create_user,
    authenticate_user,
    create_access_token,
    create_refresh_token,
    store_refresh_token,
    validate_refresh_token,
    revoke_refresh_token,
    revoke_all_user_tokens,
    get_user_by_id,
    link_broker_token,
    get_broker_info,
    change_password,
    create_password_reset_token,
    reset_password,
    complete_onboarding,
)

logger = logging.getLogger(__name__)

auth_bp = Blueprint("auth", __name__, url_prefix="/api/auth")


# ---------------------------------------------------------------------------
# Rate-limit auth endpoints (imported in app.py via limiter)
# ---------------------------------------------------------------------------


@auth_bp.route("/register", methods=["POST"])
@limiter.limit("5 per minute")
@validate_request(RegisterBody)
def register(body: RegisterBody):
    """Register a new user account."""
    try:
        user = create_user(body.email, body.password, body.name)

        # Issue tokens immediately (auto-login after registration)
        access_token = create_access_token(user["id"], user["email"])
        raw_refresh, refresh_hash = create_refresh_token(user["id"])
        store_refresh_token(user["id"], refresh_hash)

        return jsonify({
            "success": True,
            "access_token": access_token,
            "refresh_token": raw_refresh,
            "user": {"id": user["id"], "email": user["email"], "name": user["name"]},
        }), 201

    except ValueError as e:
        return jsonify({"success": False, "error": str(e)}), 409
    except Exception as e:
        logger.exception("[Auth] Registration failed")
        return jsonify({"success": False, "error": "Registration failed"}), 500


@auth_bp.route("/login", methods=["POST"])
@limiter.limit("5 per minute")
@validate_request(LoginBody)
def login(body: LoginBody):
    """Login with email + password."""
    try:
        user = authenticate_user(body.email, body.password)
        if not user:
            return jsonify({"success": False, "error": "Invalid email or password"}), 401

        access_token = create_access_token(user["id"], user["email"])
        raw_refresh, refresh_hash = create_refresh_token(user["id"])
        store_refresh_token(user["id"], refresh_hash)

        # Include broker link status
        broker_info = get_broker_info(user["id"])

        return jsonify({
            "success": True,
            "access_token": access_token,
            "refresh_token": raw_refresh,
            "user": {
                "id": user["id"],
                "email": user["email"],
                "name": user["name"],
                "is_admin": bool(user.get("is_admin", False)),
                "onboarding_completed": bool(user.get("onboarding_completed", False)),
            },
            "broker_linked": broker_info is not None,
        })

    except Exception as e:
        logger.exception("[Auth] Login failed")
        return jsonify({"success": False, "error": "Login failed"}), 500


@auth_bp.route("/refresh", methods=["POST"])
@validate_request(RefreshBody)
def refresh(body: RefreshBody):
    """Get a new access token using a refresh token."""
    try:
        raw_refresh = body.refresh_token
        user_id = validate_refresh_token(raw_refresh)
        if user_id is None:
            return jsonify({"success": False, "error": "Invalid or expired refresh token"}), 401

        user = get_user_by_id(user_id)
        if not user or not user.get("is_active"):
            return jsonify({"success": False, "error": "User not found or deactivated"}), 401

        # Rotate: revoke old, issue new pair
        revoke_refresh_token(raw_refresh)
        access_token = create_access_token(user["id"], user["email"])
        new_raw_refresh, new_refresh_hash = create_refresh_token(user["id"])
        store_refresh_token(user["id"], new_refresh_hash)

        return jsonify({
            "success": True,
            "access_token": access_token,
            "refresh_token": new_raw_refresh,
        })

    except Exception as e:
        logger.exception("[Auth] Token refresh failed")
        return jsonify({"success": False, "error": "Token refresh failed"}), 500


@auth_bp.route("/me", methods=["GET"])
@require_auth
def get_me():
    """Get current user profile + broker link status + tier."""
    user = g.current_user
    broker_info = get_broker_info(user["id"])
    from services.tier_service import get_user_tier_info
    tier_info = get_user_tier_info(user["id"])

    return jsonify({
        "success": True,
        "user": {
            "id": user["id"],
            "email": user["email"],
            "name": user["name"],
            "is_admin": user.get("is_admin", False),
            "onboarding_completed": user.get("onboarding_completed", False),
        },
        "broker_linked": broker_info is not None,
        "broker": {
            "broker_user_id": broker_info["broker_user_id"],
            "broker_user_name": broker_info["broker_user_name"],
            "linked_at": broker_info["linked_at"],
        } if broker_info else None,
        "tier": tier_info,
    })


@auth_bp.route("/logout", methods=["POST"])
@require_auth
def logout():
    """Logout — revoke all refresh tokens for the user."""
    user = g.current_user
    revoke_all_user_tokens(user["id"])
    return jsonify({"success": True, "message": "Logged out"})


# ---------------------------------------------------------------------------
# Password management
# ---------------------------------------------------------------------------

@auth_bp.route("/change-password", methods=["POST"])
@limiter.limit("3 per minute")
@require_auth
@validate_request(ChangePasswordBody)
def change_pwd(body: ChangePasswordBody):
    """Change the current user's password. Revokes all sessions."""
    try:
        change_password(g.current_user["id"], body.current_password, body.new_password)
        return jsonify({"success": True, "message": "Password changed. Please log in again."})
    except ValueError as e:
        return jsonify({"success": False, "error": str(e)}), 400
    except Exception:
        logger.exception("[Auth] Password change failed")
        return jsonify({"success": False, "error": "Password change failed"}), 500


@auth_bp.route("/forgot-password", methods=["POST"])
@limiter.limit("5 per minute")
@validate_request(ForgotPasswordBody)
def forgot_password(body: ForgotPasswordBody):
    """Request a password reset token. Always returns 200 to prevent email enumeration."""
    token = create_password_reset_token(body.email)
    if token:
        logger.info("[Auth] Password reset token generated for %s (token=%s)", body.email, token)
    return jsonify({
        "success": True,
        "message": "If that email is registered, a reset link has been generated. Check server logs.",
    })


@auth_bp.route("/reset-password", methods=["POST"])
@limiter.limit("5 per minute")
@validate_request(ResetPasswordBody)
def reset_pwd(body: ResetPasswordBody):
    """Reset password using a valid reset token."""
    try:
        reset_password(body.token, body.new_password)
        return jsonify({"success": True, "message": "Password reset successfully. Please log in."})
    except ValueError as e:
        return jsonify({"success": False, "error": str(e)}), 400
    except Exception:
        logger.exception("[Auth] Password reset failed")
        return jsonify({"success": False, "error": "Password reset failed"}), 500


# ---------------------------------------------------------------------------
# Broker linking (Kite OAuth flow)
# ---------------------------------------------------------------------------

@auth_bp.route("/broker/login-url", methods=["GET"])
@require_auth
def get_broker_login_url():
    """Get Zerodha login URL for broker linking."""
    try:
        broker = KiteBrokerAdapter()
        login_url = broker.login_url()
        return jsonify({"success": True, "login_url": login_url})
    except Exception as e:
        logger.exception("[Auth] Failed to get broker login URL")
        return jsonify({"success": False, "error": "Failed to get login URL"}), 500


@auth_bp.route("/broker/link", methods=["POST"])
@require_auth
@validate_request(BrokerLinkBody)
def link_broker(body: BrokerLinkBody):
    """Exchange Kite request_token and link broker to user account."""
    try:
        broker = KiteBrokerAdapter()
        session_data = broker.generate_session(body.request_token)
        access_token = session_data["access_token"]

        broker.set_access_token(access_token)
        profile = broker.profile()

        # Store broker token linked to user
        user = g.current_user
        link_broker_token(
            user_id=user["id"],
            access_token=access_token,
            broker="kite",
            broker_user_id=profile.get("user_id"),
            broker_user_name=profile.get("user_name"),
            broker_email=profile.get("email"),
        )

        return jsonify({
            "success": True,
            "message": "Broker linked successfully",
            "broker": {
                "broker_user_id": profile.get("user_id"),
                "broker_user_name": profile.get("user_name"),
            },
        })

    except Exception as e:
        logger.exception("[Auth] Broker linking failed")
        return jsonify({"success": False, "error": "Failed to link broker account"}), 500


@auth_bp.route("/broker/status", methods=["GET"])
@require_auth
def broker_status():
    """Check if broker is linked and token is still valid."""
    user = g.current_user
    broker_info = get_broker_info(user["id"])

    if not broker_info:
        return jsonify({"success": True, "linked": False})

    # Try to verify the token is still valid
    try:
        broker = get_broker(broker_info["access_token"])
        broker.profile()
        return jsonify({
            "success": True,
            "linked": True,
            "valid": True,
            "broker_user_id": broker_info["broker_user_id"],
            "broker_user_name": broker_info["broker_user_name"],
        })
    except Exception:
        return jsonify({
            "success": True,
            "linked": True,
            "valid": False,
            "message": "Broker token expired. Please re-link your account.",
        })


# ---------------------------------------------------------------------------
# Tier & onboarding
# ---------------------------------------------------------------------------

@auth_bp.route("/tier", methods=["GET"])
@require_auth
def get_tier():
    """Get current user's tier info."""
    from services.tier_service import get_user_tier_info
    return jsonify({"success": True, **get_user_tier_info(g.current_user["id"])})


@auth_bp.route("/onboarding-status", methods=["GET"])
@require_auth
def onboarding_status():
    """Get onboarding status + tier info."""
    from services.tier_service import get_user_tier_info
    user = g.current_user
    return jsonify({
        "success": True,
        "onboarding_completed": user.get("onboarding_completed", False),
        "tier_info": get_user_tier_info(user["id"]),
    })


@auth_bp.route("/onboarding-complete", methods=["POST"])
@require_auth
def onboarding_complete():
    """Mark onboarding as completed for the current user."""
    try:
        complete_onboarding(g.current_user["id"])
        return jsonify({"success": True, "message": "Onboarding completed"})
    except Exception:
        logger.exception("[Auth] Failed to complete onboarding")
        return jsonify({"success": False, "error": "Failed to update onboarding status"}), 500


# ---------------------------------------------------------------------------
# Subscription (dummy paywall — swap out when payment gateway is ready)
# ---------------------------------------------------------------------------

@auth_bp.route("/subscription", methods=["GET"])
@require_auth
def get_subscription():
    """Return subscription status. Currently always returns inactive (dummy)."""
    return jsonify({
        "success": True,
        "active": False,
        "plan": None,
        "message": "No active subscription",
    })


@auth_bp.route("/subscription/activate", methods=["POST"])
@require_auth
def activate_subscription():
    """Dummy subscription activation. Replace with real payment gateway later."""
    return jsonify({
        "success": True,
        "active": True,
        "message": "Subscription activated (demo mode — no charge applied)",
    })


# ---------------------------------------------------------------------------
# Per-user LLM API keys (BYOK)
# ---------------------------------------------------------------------------

@auth_bp.route("/llm-keys", methods=["GET"])
@require_auth
def get_llm_keys():
    """Return list of providers the user has configured. Never returns raw keys."""
    from services.llm_key_service import get_user_llm_providers
    providers = get_user_llm_providers(g.current_user["id"])
    return jsonify({"success": True, "providers": providers})


@auth_bp.route("/llm-keys", methods=["POST"])
@require_auth
@validate_request(LLMKeyBody)
def save_llm_key(body: LLMKeyBody):
    """Validate and store a user's LLM API key."""
    from services.llm_key_service import store_llm_key, validate_llm_key
    try:
        if not validate_llm_key(body.provider, body.api_key):
            return jsonify({
                "success": False,
                "error": f"API key validation failed for provider '{body.provider}'. "
                         "Please check the key and try again.",
            }), 400

        store_llm_key(g.current_user["id"], body.provider, body.api_key)
        return jsonify({"success": True, "message": f"{body.provider} key saved successfully"})

    except Exception:
        logger.exception("[Auth] Failed to save LLM key")
        return jsonify({"success": False, "error": "Failed to save API key"}), 500


@auth_bp.route("/llm-keys/<provider>", methods=["DELETE"])
@require_auth
def delete_llm_key(provider: str):
    """Remove a user's stored LLM API key."""
    from services.llm_key_service import delete_llm_key, VALID_PROVIDERS
    if provider not in VALID_PROVIDERS:
        return jsonify({"success": False, "error": f"Unknown provider '{provider}'"}), 400
    try:
        deleted = delete_llm_key(g.current_user["id"], provider)
        if not deleted:
            return jsonify({"success": False, "error": "No key found for that provider"}), 404
        return jsonify({"success": True, "message": f"{provider} key removed"})
    except Exception:
        logger.exception("[Auth] Failed to delete LLM key")
        return jsonify({"success": False, "error": "Failed to remove API key"}), 500


# ---------------------------------------------------------------------------
# User plan management
# ---------------------------------------------------------------------------

@auth_bp.route("/plan", methods=["GET"])
@require_auth
def get_plan():
    """Return the user's selected plan and tier info."""
    from services.tier_service import get_user_tier_info
    info = get_user_tier_info(g.current_user["id"])
    return jsonify({"success": True, **info})


@auth_bp.route("/plan", methods=["POST"])
@require_auth
def set_plan():
    """Set the user's selected plan."""
    from services.tier_service import set_user_plan, VALID_PLANS
    data = request.json or {}
    plan = data.get("plan", "")
    if plan not in VALID_PLANS:
        return jsonify({"success": False, "error": f"Invalid plan. Must be one of: {sorted(VALID_PLANS)}"}), 400
    try:
        set_user_plan(g.current_user["id"], plan)
        from services.tier_service import get_user_tier_info
        info = get_user_tier_info(g.current_user["id"])
        return jsonify({"success": True, "message": f"Plan updated to '{plan}'", **info})
    except Exception:
        logger.exception("[Auth] Failed to set plan")
        return jsonify({"success": False, "error": "Failed to update plan"}), 500
