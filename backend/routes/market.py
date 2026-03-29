"""Market data endpoints — /api/market/*"""

import csv
import logging
from pathlib import Path

from flask import Blueprint, request, jsonify, g

from broker import get_broker
from middleware.auth import require_auth, require_broker

logger = logging.getLogger(__name__)

market_bp = Blueprint("market", __name__, url_prefix="/api/market")

# Path to nifty100 CSV — used for top gainers/losers
_NIFTY100_CSV = Path(__file__).resolve().parents[1] / "data" / "nifty100.csv"


def _load_nifty100_symbols() -> list[str]:
    """Return list of NSE symbols from nifty100.csv."""
    symbols = []
    try:
        with open(_NIFTY100_CSV, newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                sym = row.get("symbol", "").strip()
                if sym:
                    symbols.append(sym)
    except Exception as e:
        logger.warning(f"Failed to load nifty100.csv: {e}")
    return symbols


@market_bp.route("/indices", methods=["GET"])
@require_auth
@require_broker
def get_market_indices():
    """Get Nifty 50 and Sensex indices data using Kite API."""
    try:
        broker = get_broker(g.broker_token)
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

        return jsonify({
            "success": True,
            "nifty": format_index_data(nifty_quote, "NIFTY 50"),
            "sensex": format_index_data(sensex_quote, "SENSEX"),
        })

    except Exception as e:
        logger.error(f"Market indices API failed: {e}")
        return jsonify({"success": False, "error": "Failed to fetch market indices"}), 503


@market_bp.route("/top-stocks", methods=["GET"])
@require_auth
@require_broker
def get_top_stocks():
    """Get top gainers and losers from Nifty 100 using live Kite API quotes."""
    try:
        symbols = _load_nifty100_symbols()
        if not symbols:
            return jsonify({"success": False, "error": "Could not load Nifty 100 symbol list"}), 500

        broker = get_broker(g.broker_token)

        instrument_keys = [f"NSE:{sym}" for sym in symbols]
        quotes = broker.get_quote(instrument_keys)

        stocks = []
        for key, quote in quotes.items():
            sym = key.replace("NSE:", "")
            last_price = quote.get("last_price", 0)
            ohlc = quote.get("ohlc", {})
            open_price = ohlc.get("open", last_price)

            if open_price <= 0 or last_price <= 0:
                continue

            change = last_price - open_price
            change_percent = (change / open_price) * 100

            stocks.append({
                "symbol": sym,
                "name": sym,
                "price": round(last_price, 2),
                "change": round(change, 2),
                "change_percent": round(change_percent, 2),
                "high": round(ohlc.get("high", 0), 2),
                "low": round(ohlc.get("low", 0), 2),
                "volume": quote.get("volume", 0),
            })

        stocks.sort(key=lambda x: x["change_percent"], reverse=True)
        top_gainers = stocks[:10]
        top_losers = list(reversed(stocks[-10:]))

        return jsonify({
            "success": True,
            "top_gainers": top_gainers,
            "top_losers": top_losers,
        })

    except Exception as e:
        logger.error(f"Top stocks API failed: {e}")
        return jsonify({"success": False, "error": "Failed to fetch top stocks"}), 503
