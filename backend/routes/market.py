"""Market data endpoints — /api/market/*"""

import logging

from flask import Blueprint, request, jsonify

from broker import get_broker
from services.market_data import simulate_live_market_data, simulate_live_stock_data

logger = logging.getLogger(__name__)

market_bp = Blueprint("market", __name__, url_prefix="/api/market")


@market_bp.route("/indices", methods=["POST"])
def get_market_indices():
    """Get Nifty 50 and Sensex indices data using Kite API."""
    try:
        data = request.json
        access_token = data.get("access_token")

        if not access_token:
            return jsonify({"success": False, "error": "Access token is required"}), 400

        broker = get_broker(access_token)
        quotes = broker.get_quote(["NSE:NIFTY 50", "BSE:SENSEX"])

        nifty_quote = quotes.get("NSE:NIFTY 50", {})
        sensex_quote = quotes.get("BSE:SENSEX", {})

        def format_index_data(quote, name):
            last_price = quote.get("last_price", 0)
            ohlc = quote.get("ohlc", {})
            open_price = ohlc.get("open", last_price)
            change = last_price - open_price
            change_percent = (change / open_price * 100) if open_price > 0 else 0

            return {
                "name": name,
                "value": round(last_price, 2),
                "change": round(change, 2),
                "change_percent": round(change_percent, 2),
                "high": round(ohlc.get("high", 0), 2),
                "low": round(ohlc.get("low", 0), 2),
                "volume": quote.get("volume", 0),
            }

        return jsonify(
            {
                "success": True,
                "nifty": format_index_data(nifty_quote, "NIFTY 50"),
                "sensex": format_index_data(sensex_quote, "SENSEX"),
            }
        )

    except Exception as e:
        market_data = simulate_live_market_data()
        return jsonify(
            {
                "success": True,
                "nifty": market_data["nifty"],
                "sensex": market_data["sensex"],
                "note": f"Live simulation - API Error: {str(e)}",
            }
        )


@market_bp.route("/top-stocks", methods=["GET"])
def get_top_stocks():
    """Get top 10 gainers and losers with live simulation."""
    try:
        stock_data = simulate_live_stock_data()
        return jsonify(
            {
                "success": True,
                "top_gainers": stock_data["top_gainers"],
                "top_losers": stock_data["top_losers"],
                "note": "Live market simulation",
            }
        )
    except Exception as e:
        return jsonify(
            {"success": False, "error": f"Failed to generate market data: {str(e)}"}
        ), 500
