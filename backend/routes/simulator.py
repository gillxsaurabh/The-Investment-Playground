"""Simulator endpoints — /api/simulator/*"""

import logging
import threading

from flask import Blueprint, request, jsonify

from broker import get_broker
from services.simulator_engine import PaperTradingSimulator, start_position_monitor
from constants import DEFAULT_INITIAL_CAPITAL

logger = logging.getLogger(__name__)

simulator_bp = Blueprint("simulator", __name__, url_prefix="/api/simulator")

# Simulator singleton
_simulator_instance = None
_simulator_lock = threading.Lock()
_simulator_token = None


def _get_simulator(access_token: str) -> PaperTradingSimulator:
    """Get or create the simulator singleton, updating the Kite access token if it changed."""
    global _simulator_instance, _simulator_token
    with _simulator_lock:
        if _simulator_instance is None:
            broker = get_broker(access_token)
            _simulator_instance = PaperTradingSimulator(broker.raw_kite)
            _simulator_token = access_token
            start_position_monitor(_simulator_instance)
        elif access_token != _simulator_token:
            # Token changed (new login / new day) — update the Kite instance
            _simulator_instance.kite.set_access_token(access_token)
            _simulator_token = access_token
        return _simulator_instance


@simulator_bp.route("/execute", methods=["POST"])
def simulator_execute():
    """Execute a virtual buy order."""
    try:
        data = request.json
        access_token = data.get("access_token")
        if not access_token:
            return jsonify({"success": False, "error": "No access token"}), 401

        sim = _get_simulator(access_token)
        result = sim.execute_order(
            symbol=data["symbol"],
            quantity=data["quantity"],
            atr_at_entry=data["atr"],
            trail_multiplier=data.get("trail_multiplier", 1.5),
            instrument_token=data.get("instrument_token"),
        )
        status = 200 if result.get("success") else 400
        return jsonify(result), status

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@simulator_bp.route("/positions", methods=["POST"])
def simulator_positions():
    """Get active positions with live P&L."""
    try:
        data = request.json
        access_token = data.get("access_token")
        if not access_token:
            return jsonify({"success": False, "error": "No access token"}), 401

        sim = _get_simulator(access_token)
        result = sim.get_positions_with_pnl()
        return jsonify({"success": True, **result})

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@simulator_bp.route("/close", methods=["POST"])
def simulator_close():
    """Close a virtual position."""
    try:
        data = request.json
        access_token = data.get("access_token")
        if not access_token:
            return jsonify({"success": False, "error": "No access token"}), 401

        sim = _get_simulator(access_token)
        result = sim.close_position(trade_id=data["trade_id"])
        status = 200 if result.get("success") else 404
        return jsonify(result), status

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@simulator_bp.route("/reset", methods=["POST"])
def simulator_reset():
    """Reset the simulator."""
    try:
        data = request.json
        access_token = data.get("access_token")
        if not access_token:
            return jsonify({"success": False, "error": "No access token"}), 401

        sim = _get_simulator(access_token)
        initial_capital = data.get("initial_capital", DEFAULT_INITIAL_CAPITAL)
        result = sim.reset(initial_capital)
        return jsonify(result)

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@simulator_bp.route("/status", methods=["POST"])
def simulator_status():
    """Get simulator account summary."""
    try:
        data = request.json
        access_token = data.get("access_token")
        if not access_token:
            return jsonify({"success": False, "error": "No access token"}), 401

        sim = _get_simulator(access_token)
        summary = sim.get_account_summary()
        return jsonify({"success": True, **summary})

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@simulator_bp.route("/price-history", methods=["POST"])
def simulator_price_history():
    """Get price history snapshots for charting."""
    try:
        data = request.json
        access_token = data.get("access_token")
        if not access_token:
            return jsonify({"success": False, "error": "No access token"}), 401

        sim = _get_simulator(access_token)
        minutes = data.get("minutes", 60)
        history = sim.get_price_history(minutes)
        return jsonify({"success": True, "history": history})

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500
