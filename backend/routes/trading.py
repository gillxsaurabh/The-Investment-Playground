"""Unified trading routes — /api/trading/*

Routes all trading actions through the TradingEngine interface so the same
endpoints work in both simulator and live mode. Mode is controlled via
POST /api/trading/mode.
"""

import logging

from flask import Blueprint, jsonify, request

logger = logging.getLogger(__name__)

trading_bp = Blueprint("trading", __name__, url_prefix="/api/trading")


def _get_engine(access_token: str, mode: str = None):
    from services.engine_factory import get_trading_engine
    return get_trading_engine(access_token, mode)


@trading_bp.route("/mode", methods=["GET"])
def get_mode():
    """Return current trading mode."""
    from services.engine_factory import get_current_mode
    return jsonify({"success": True, "mode": get_current_mode()})


@trading_bp.route("/mode", methods=["POST"])
def set_mode():
    """Set trading mode. Requires confirm=true when switching to live."""
    data = request.get_json(silent=True) or {}
    mode = data.get("mode")
    confirm = data.get("confirm", False)

    if mode not in ("simulator", "live"):
        return jsonify({"success": False, "error": "mode must be 'simulator' or 'live'"}), 400

    if mode == "live" and not confirm:
        return jsonify({
            "success": False,
            "error": "Set confirm=true to switch to live trading. This uses real money.",
            "requires_confirm": True,
        }), 400

    from services.engine_factory import set_trading_mode
    set_trading_mode(mode)
    logger.info(f"[Trading] Mode switched to '{mode}'")
    return jsonify({"success": True, "mode": mode, "message": f"Trading mode set to '{mode}'"})


@trading_bp.route("/execute", methods=["POST"])
def execute_order():
    """Execute a buy order through the active engine."""
    try:
        data = request.json
        access_token = data.get("access_token")
        if not access_token:
            return jsonify({"success": False, "error": "No access token"}), 401

        engine = _get_engine(access_token)
        result = engine.execute_order(
            symbol=data["symbol"],
            quantity=data["quantity"],
            atr_at_entry=data["atr"],
            trail_multiplier=data.get("trail_multiplier", 1.5),
            instrument_token=data.get("instrument_token"),
            ltp=data.get("ltp"),
            automation_run_id=data.get("automation_run_id"),
            automation_gear=data.get("automation_gear"),
        )
        status = 200 if result.get("success") else 400
        return jsonify(result), status

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@trading_bp.route("/positions", methods=["POST"])
def get_positions():
    """Get active positions with live P&L from the active engine."""
    try:
        data = request.json
        access_token = data.get("access_token")
        if not access_token:
            return jsonify({"success": False, "error": "No access token"}), 401

        engine = _get_engine(access_token)
        result = engine.get_positions_with_pnl()
        return jsonify({"success": True, "mode": engine.mode, **result})

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@trading_bp.route("/close", methods=["POST"])
def close_position():
    """Close a position through the active engine."""
    try:
        data = request.json
        access_token = data.get("access_token")
        if not access_token:
            return jsonify({"success": False, "error": "No access token"}), 401

        engine = _get_engine(access_token)
        result = engine.close_position(
            trade_id=data["trade_id"],
            reason=data.get("reason", "Manual Close"),
        )
        status = 200 if result.get("success") else 404
        return jsonify(result), status

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@trading_bp.route("/status", methods=["POST"])
def account_status():
    """Get account summary from the active engine."""
    try:
        data = request.json
        access_token = data.get("access_token")
        if not access_token:
            return jsonify({"success": False, "error": "No access token"}), 401

        engine = _get_engine(access_token)
        summary = engine.get_account_summary()
        return jsonify({"success": True, "mode": engine.mode, **summary})

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@trading_bp.route("/price-history", methods=["POST"])
def price_history():
    """Get price history snapshots for charting."""
    try:
        data = request.json
        access_token = data.get("access_token")
        if not access_token:
            return jsonify({"success": False, "error": "No access token"}), 401

        engine = _get_engine(access_token)
        minutes = data.get("minutes", 60)
        history = engine.get_price_history(minutes)
        return jsonify({"success": True, "mode": engine.mode, "history": history})

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@trading_bp.route("/orders", methods=["POST"])
def get_orders():
    """Today's orders. Live: from Kite API. Simulator: empty list."""
    try:
        data = request.json
        access_token = data.get("access_token")
        if not access_token:
            return jsonify({"success": False, "error": "No access token"}), 401

        engine = _get_engine(access_token)
        if engine.mode == "live":
            from broker import get_broker
            broker = get_broker(access_token)
            orders = broker.get_orders()
            return jsonify({"success": True, "mode": "live", "orders": orders})
        else:
            return jsonify({"success": True, "mode": "simulator", "orders": []})

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@trading_bp.route("/reconcile", methods=["POST"])
def reconcile():
    """Trigger position reconciliation against Kite holdings (live mode only)."""
    try:
        data = request.json
        access_token = data.get("access_token")
        if not access_token:
            return jsonify({"success": False, "error": "No access token"}), 401

        engine = _get_engine(access_token)
        if engine.mode != "live":
            return jsonify({"success": False, "error": "Reconcile only applicable in live mode"}), 400

        result = engine.reconcile_positions()
        return jsonify(result)

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500
