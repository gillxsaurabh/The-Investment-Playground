"""Automation control routes — /api/automation/*

Provides endpoints to:
  - GET  /status   — current automation state + next run time
  - POST /enable   — enable or disable automation (and set mode)
  - POST /run-now  — trigger automation immediately (for testing)
  - GET  /history  — last 10 automation run records
"""

import logging
import threading
from flask import Blueprint, request, jsonify

from automation.weekly_trader import run_weekly_automation, _load_state, _save_state
from automation.scheduler import get_next_run_time, is_running

logger = logging.getLogger(__name__)

automation_bp = Blueprint("automation", __name__, url_prefix="/api/automation")

# Track if a run-now job is already executing (prevents double-triggers)
_run_now_lock = threading.Lock()
_run_now_active = False


@automation_bp.route("/status", methods=["GET"])
def automation_status():
    """Return current automation configuration and last run summary."""
    state = _load_state()
    return jsonify({
        "success": True,
        "enabled": state.get("enabled", False),
        "mode": state.get("mode", "simulator"),
        "scheduler_running": is_running(),
        "next_run": get_next_run_time(),
        "last_run": state.get("last_run"),
    })


@automation_bp.route("/enable", methods=["POST"])
def automation_enable():
    """Enable or disable automation and optionally set the execution mode.

    Body: { "enabled": true/false, "mode": "simulator" | "live" }
    """
    data = request.get_json(silent=True) or {}
    enabled = data.get("enabled")
    mode = data.get("mode")

    if enabled is None:
        return jsonify({"success": False, "error": "Missing 'enabled' field"}), 400
    if mode not in (None, "simulator", "live"):
        return jsonify({"success": False, "error": "mode must be 'simulator' or 'live'"}), 400

    state = _load_state()
    state["enabled"] = bool(enabled)
    if mode is not None:
        state["mode"] = mode
    _save_state(state)

    status_str = "enabled" if enabled else "disabled"
    mode_str = state.get("mode", "simulator")
    logger.info(f"[Automation] {status_str.capitalize()} via API (mode={mode_str})")

    return jsonify({
        "success": True,
        "enabled": state["enabled"],
        "mode": mode_str,
        "message": f"Automation {status_str} (mode: {mode_str})",
    })


@automation_bp.route("/run-now", methods=["POST"])
def automation_run_now():
    """Trigger the automation immediately (for testing / manual runs).

    Body: { "access_token": "...", "dry_run": true/false }

    If dry_run=true, runs discovery only without executing trades.
    This endpoint runs synchronously and may take 30+ minutes.
    Use with care.
    """
    global _run_now_active

    data = request.get_json(silent=True) or {}
    dry_run = bool(data.get("dry_run", True))
    access_token = data.get("access_token", "")

    # If an access_token is provided, temporarily persist it so the automation
    # job can read it from the state file (the scheduler reads from TOKEN_FILE)
    if access_token:
        import json
        from config import TOKEN_FILE
        from pathlib import Path
        path = Path(TOKEN_FILE)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            json.dump({"access_token": access_token}, f)

    with _run_now_lock:
        if _run_now_active:
            return jsonify({
                "success": False,
                "error": "A run-now is already in progress. Please wait.",
            }), 429
        _run_now_active = True

    try:
        logger.info(f"[Automation] run-now triggered via API (dry_run={dry_run})")
        result = run_weekly_automation(dry_run=dry_run)
        return jsonify({"success": True, **result})
    except Exception as e:
        logger.error(f"[Automation] run-now failed: {e}", exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 500
    finally:
        with _run_now_lock:
            _run_now_active = False


@automation_bp.route("/history", methods=["GET"])
def automation_history():
    """Return the last 10 automation run records."""
    state = _load_state()
    return jsonify({
        "success": True,
        "history": state.get("history", []),
    })
