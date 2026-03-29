"""Simulator endpoints — /api/simulator/*"""

import logging
import threading
from pathlib import Path
from typing import Dict, Tuple

from flask import Blueprint, request, jsonify, g

from broker import get_broker
from config import STATE_DIR
from middleware.auth import require_auth, require_broker
from services.simulator_engine import PaperTradingSimulator, start_position_monitor
from services.validation import validate_request, SimulatorExecuteBody, SimulatorCloseBody, SimulatorResetBody
from constants import DEFAULT_INITIAL_CAPITAL

logger = logging.getLogger(__name__)

simulator_bp = Blueprint("simulator", __name__, url_prefix="/api/simulator")

# Per-user simulator instances: {user_id: (PaperTradingSimulator, access_token)}
_simulators: Dict[int, Tuple[PaperTradingSimulator, str]] = {}
_simulators_lock = threading.Lock()


def _user_simulator_files(user_id: int):
    """Return per-user simulator data and price-history file paths."""
    data_file = STATE_DIR / f"simulator_data_{user_id}.json"
    history_file = STATE_DIR / f"simulator_price_history_{user_id}.json"
    return data_file, history_file


def _get_simulator(user_id: int, access_token: str) -> PaperTradingSimulator:
    """Get or create a per-user simulator instance, refreshing the token if it changed."""
    with _simulators_lock:
        if user_id in _simulators:
            sim, prev_token = _simulators[user_id]
            if access_token != prev_token:
                sim.kite.set_access_token(access_token)
                _simulators[user_id] = (sim, access_token)
            return sim

        # First time for this user — create a new instance
        broker = get_broker(access_token)
        data_file, history_file = _user_simulator_files(user_id)
        sim = PaperTradingSimulator(
            broker.raw_kite,
            data_file=data_file,
            history_file=history_file,
            user_id=user_id,
        )
        start_position_monitor(sim)
        _simulators[user_id] = (sim, access_token)
        return sim


@simulator_bp.route("/execute", methods=["POST"])
@require_auth
@require_broker
@validate_request(SimulatorExecuteBody)
def simulator_execute(body: SimulatorExecuteBody):
    """Execute a virtual buy order."""
    try:
        sim = _get_simulator(g.current_user["id"], g.broker_token)
        result = sim.execute_order(
            symbol=body.symbol,
            quantity=body.quantity,
            atr_at_entry=body.atr,
            trail_multiplier=body.trail_multiplier,
            instrument_token=body.instrument_token,
            ltp=body.ltp,
        )
        status = 200 if result.get("success") else 400
        return jsonify(result), status

    except Exception as e:
        return jsonify({"success": False, "error": "Failed to execute order"}), 500


@simulator_bp.route("/positions", methods=["GET"])
@require_auth
@require_broker
def simulator_positions():
    """Get active positions with live P&L."""
    try:
        sim = _get_simulator(g.current_user["id"], g.broker_token)
        result = sim.get_positions_with_pnl()
        return jsonify({"success": True, **result})

    except Exception as e:
        return jsonify({"success": False, "error": "Failed to fetch positions"}), 500


@simulator_bp.route("/close", methods=["POST"])
@require_auth
@require_broker
@validate_request(SimulatorCloseBody)
def simulator_close(body: SimulatorCloseBody):
    """Close a virtual position."""
    try:
        sim = _get_simulator(g.current_user["id"], g.broker_token)
        result = sim.close_position(trade_id=body.trade_id)
        status = 200 if result.get("success") else 404
        return jsonify(result), status

    except Exception as e:
        return jsonify({"success": False, "error": "Failed to close position"}), 500


@simulator_bp.route("/reset", methods=["POST"])
@require_auth
@require_broker
@validate_request(SimulatorResetBody)
def simulator_reset(body: SimulatorResetBody):
    """Reset the simulator."""
    try:
        sim = _get_simulator(g.current_user["id"], g.broker_token)
        result = sim.reset(body.initial_capital)
        return jsonify(result)

    except Exception as e:
        return jsonify({"success": False, "error": "Failed to reset simulator"}), 500


@simulator_bp.route("/status", methods=["GET"])
@require_auth
@require_broker
def simulator_status():
    """Get simulator account summary."""
    try:
        sim = _get_simulator(g.current_user["id"], g.broker_token)
        summary = sim.get_account_summary()
        return jsonify({"success": True, **summary})

    except Exception as e:
        return jsonify({"success": False, "error": "Failed to fetch status"}), 500


@simulator_bp.route("/price-history", methods=["GET"])
@require_auth
@require_broker
def simulator_price_history():
    """Get price history snapshots for charting."""
    try:
        sim = _get_simulator(g.current_user["id"], g.broker_token)
        minutes = request.args.get("minutes", 60, type=int)
        history = sim.get_price_history(minutes)
        return jsonify({"success": True, "history": history})

    except Exception as e:
        return jsonify({"success": False, "error": "Failed to fetch price history"}), 500
