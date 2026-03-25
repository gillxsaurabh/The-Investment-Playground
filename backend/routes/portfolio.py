"""Portfolio endpoints — /api/portfolio/*"""

import logging
from datetime import datetime

from flask import Blueprint, request, jsonify

from broker import get_broker
from services.analysis_storage import get_saved_analysis
from services.market_data import simulate_portfolio_data
from stock_health_service import StockHealthService
from config import GEMINI_API_KEY

logger = logging.getLogger(__name__)

portfolio_bp = Blueprint("portfolio", __name__, url_prefix="/api/portfolio")


@portfolio_bp.route("/holdings", methods=["POST"])
def get_holdings():
    """Get user holdings with saved analysis data."""
    try:
        data = request.json
        access_token = data.get("access_token")

        if not access_token:
            return jsonify({"success": False, "error": "Access token is required"}), 400

        broker = get_broker(access_token)
        holdings = broker.get_holdings()

        # Enhance holdings with saved analysis data
        enhanced_holdings = []
        for holding in holdings:
            symbol = holding.get("tradingsymbol", "")
            saved_analysis = get_saved_analysis(access_token, symbol)

            enhanced_holding = {**holding}
            if saved_analysis:
                enhanced_holding["saved_analysis"] = saved_analysis["analysis"]
                enhanced_holding["analysis_saved_at"] = saved_analysis["saved_at"]
                enhanced_holding["has_saved_analysis"] = True
            else:
                enhanced_holding["has_saved_analysis"] = False

            enhanced_holdings.append(enhanced_holding)

        return jsonify({"success": True, "holdings": enhanced_holdings})

    except Exception as e:
        # Fallback to simulation
        logger.warning(f"Holdings API failed, using simulation: {e}")
        return _simulate_holdings_response(request)


@portfolio_bp.route("/positions", methods=["POST"])
def get_positions():
    """Get user positions."""
    try:
        data = request.json
        access_token = data.get("access_token")

        if not access_token:
            return jsonify({"success": False, "error": "Access token is required"}), 400

        broker = get_broker(access_token)
        positions = broker.get_positions()

        return jsonify({"success": True, "positions": positions})

    except Exception as e:
        logger.warning(f"Positions API failed, using simulation: {e}")
        return _simulate_holdings_response(request)


@portfolio_bp.route("/summary", methods=["POST"])
def get_portfolio_summary():
    """Get portfolio summary with live price updates."""
    try:
        data = request.json
        access_token = data.get("access_token")

        if not access_token:
            return jsonify({"success": False, "error": "Access token is required"}), 400

        try:
            broker = get_broker(access_token)
            holdings = broker.get_holdings()
            positions = broker.get_positions()

            total_investment = sum(h["average_price"] * h["quantity"] for h in holdings)
            current_value = sum(h["last_price"] * h["quantity"] for h in holdings)
            total_pnl = sum(h["pnl"] for h in holdings)

            return jsonify(
                {
                    "success": True,
                    "summary": {
                        "total_holdings": len(holdings),
                        "total_investment": round(total_investment, 2),
                        "current_value": round(current_value, 2),
                        "total_pnl": round(total_pnl, 2),
                        "pnl_percentage": round(
                            (total_pnl / total_investment * 100) if total_investment > 0 else 0, 2
                        ),
                        "positions_count": len(positions["net"]),
                    },
                    "note": "Real portfolio data from Kite API",
                }
            )

        except Exception as kite_error:
            logger.warning(f"Kite API failed, using simulation: {kite_error}")
            portfolio_data = simulate_portfolio_data()
            return jsonify(
                {
                    "success": True,
                    "summary": portfolio_data["summary"],
                    "note": "Simulation mode - API unavailable",
                }
            )

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@portfolio_bp.route("/top-performers", methods=["POST"])
def get_top_performers():
    """Get top 3 gainers and bottom 3 losers."""
    try:
        data = request.json
        access_token = data.get("access_token")

        if not access_token:
            return jsonify({"success": False, "error": "Access token is required"}), 400

        broker = get_broker(access_token)
        holdings = broker.get_holdings()

        if not holdings:
            return jsonify({"success": True, "top_gainers": [], "top_losers": []})

        sorted_holdings = sorted(holdings, key=lambda x: x["pnl"], reverse=True)
        top_gainers = sorted_holdings[:3]
        top_losers = sorted_holdings[-3:][::-1]

        def format_holding(h):
            return {
                "tradingsymbol": h["tradingsymbol"],
                "exchange": h["exchange"],
                "quantity": h["quantity"],
                "average_price": round(h["average_price"], 2),
                "last_price": round(h["last_price"], 2),
                "pnl": round(h["pnl"], 2),
                "pnl_percentage": round(
                    (h["pnl"] / (h["average_price"] * h["quantity"]) * 100)
                    if h["average_price"] * h["quantity"] > 0
                    else 0,
                    2,
                ),
            }

        return jsonify(
            {
                "success": True,
                "top_gainers": [format_holding(h) for h in top_gainers],
                "top_losers": [format_holding(h) for h in top_losers],
            }
        )

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@portfolio_bp.route("/health-report", methods=["POST"])
def get_health_report():
    """Get comprehensive health report for all portfolio holdings."""
    try:
        data = request.json
        access_token = data.get("access_token")

        if not access_token:
            return jsonify({"success": False, "error": "Access token is required"}), 400

        broker = get_broker(access_token)
        health_service = StockHealthService(
            kite_instance=broker.raw_kite,
            gemini_api_key=GEMINI_API_KEY,
        )

        health_reports = health_service.get_portfolio_health_report()

        return jsonify(
            {
                "success": True,
                "reports": health_reports,
                "total_stocks": len(health_reports),
                "generated_at": datetime.now().isoformat(),
            }
        )

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


def _simulate_holdings_response(req):
    """Generate simulated holdings response with saved analysis data."""
    portfolio_data = simulate_portfolio_data()
    enhanced_holdings = []

    try:
        data = req.json
        access_token = data.get("access_token", "")
    except Exception:
        access_token = ""

    for holding in portfolio_data["holdings"]:
        symbol = holding.get("tradingsymbol", "")
        enhanced_holding = {**holding}

        if access_token:
            saved_analysis = get_saved_analysis(access_token, symbol)
            if saved_analysis:
                enhanced_holding["saved_analysis"] = saved_analysis["analysis"]
                enhanced_holding["analysis_saved_at"] = saved_analysis["saved_at"]
                enhanced_holding["has_saved_analysis"] = True
            else:
                enhanced_holding["has_saved_analysis"] = False
        else:
            enhanced_holding["has_saved_analysis"] = False

        enhanced_holdings.append(enhanced_holding)

    return jsonify(
        {
            "success": True,
            "holdings": enhanced_holdings,
            "note": "Using simulation mode with saved analysis - API unavailable",
        }
    )
