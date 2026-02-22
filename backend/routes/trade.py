"""Trade endpoints — /api/trade/*"""

import logging
from datetime import datetime, timedelta

import pandas as pd
from flask import Blueprint, request, jsonify

from broker import get_broker
from services.technical import calculate_true_range

logger = logging.getLogger(__name__)

trade_bp = Blueprint("trade", __name__, url_prefix="/api/trade")


@trade_bp.route("/funds", methods=["POST"])
def get_available_funds():
    """Return available equity funds from Kite margins API."""
    try:
        data = request.json
        access_token = data.get("access_token")
        if not access_token:
            return jsonify({"success": False, "error": "access_token is required"}), 400

        broker = get_broker(access_token)
        margins = broker.get_margins("equity")
        available_funds = margins.get("available", {}).get("live_balance", 0)
        return jsonify({"success": True, "available_funds": round(float(available_funds), 2)})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@trade_bp.route("/calculate-exits", methods=["POST"])
def calculate_trade_exits():
    """Calculate ATR-based stop loss and 2:1 R:R target for a stock."""
    try:
        data = request.json
        access_token = data.get("access_token")
        symbol = data.get("symbol")
        instrument_token = data.get("instrument_token")
        ltp = data.get("ltp")

        if not all([access_token, symbol, instrument_token, ltp]):
            return (
                jsonify(
                    {
                        "success": False,
                        "error": "access_token, symbol, instrument_token, and ltp are required",
                    }
                ),
                400,
            )

        broker = get_broker(access_token)

        # Fetch 30 days of candles for ATR calculation
        to_date = datetime.now()
        from_date = to_date - timedelta(days=30)
        history = broker.get_historical_data(
            instrument_token,
            from_date.strftime("%Y-%m-%d"),
            to_date.strftime("%Y-%m-%d"),
            "day",
        )

        if not history or len(history) < 15:
            return (
                jsonify(
                    {"success": False, "error": f"Insufficient historical data for {symbol}"}
                ),
                400,
            )

        df = pd.DataFrame(history)
        # Rename to standard format for technical functions
        df.rename(
            columns={"open": "Open", "high": "High", "low": "Low", "close": "Close"},
            inplace=True,
        )

        # Calculate ATR using the shared technical function
        tr = calculate_true_range(df)
        atr = tr.tail(14).mean()

        initial_sl = ltp - (1.5 * atr)
        risk_per_share = 1.5 * atr

        return jsonify(
            {
                "success": True,
                "symbol": symbol,
                "ltp": round(ltp, 2),
                "atr": round(atr, 2),
                "initial_sl": round(initial_sl, 2),
                "trail_multiplier": 1.5,
                "risk_per_share": round(risk_per_share, 2),
            }
        )
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500
