"""Simulation fallback data for when the Kite API is unavailable.

Extracted from app.py. These functions return static market/portfolio data
used as graceful degradation when API calls fail.
"""


def simulate_live_market_data() -> dict:
    """Generate static market data (no random variations)."""
    base_nifty = 21731.45
    base_sensex = 71752.11

    return {
        "nifty": {
            "name": "NIFTY 50",
            "value": round(base_nifty, 2),
            "change": 0.0,
            "change_percent": 0.0,
            "high": round(base_nifty * 1.005, 2),
            "low": round(base_nifty * 0.995, 2),
            "volume": 0,
        },
        "sensex": {
            "name": "SENSEX",
            "value": round(base_sensex, 2),
            "change": 0.0,
            "change_percent": 0.0,
            "high": round(base_sensex * 1.005, 2),
            "low": round(base_sensex * 0.995, 2),
            "volume": 0,
        },
    }


def simulate_live_stock_data() -> dict:
    """Generate static stock data (no random variations)."""
    stocks = {
        "gainers": [
            {"symbol": "ADANIENT", "base_price": 2891.50, "base_change_percent": 3.19},
            {"symbol": "TATAMOTORS", "base_price": 965.25, "base_change_percent": 3.07},
            {"symbol": "HINDALCO", "base_price": 638.90, "base_change_percent": 2.80},
            {"symbol": "TATASTEEL", "base_price": 148.75, "base_change_percent": 2.58},
            {"symbol": "JSWSTEEL", "base_price": 901.45, "base_change_percent": 2.38},
            {"symbol": "BAJFINANCE", "base_price": 6789.30, "base_change_percent": 2.02},
            {"symbol": "MARUTI", "base_price": 10245.60, "base_change_percent": 1.84},
            {"symbol": "M&M", "base_price": 1678.25, "base_change_percent": 1.74},
            {"symbol": "LT", "base_price": 3456.80, "base_change_percent": 1.63},
            {"symbol": "RELIANCE", "base_price": 2934.65, "base_change_percent": 1.53},
        ],
        "losers": [
            {"symbol": "NESTLEIND", "base_price": 2345.80, "base_change_percent": -3.41},
            {"symbol": "BRITANNIA", "base_price": 4567.90, "base_change_percent": -2.68},
            {"symbol": "HINDUNILVR", "base_price": 2654.35, "base_change_percent": -2.40},
            {"symbol": "ITC", "base_price": 456.75, "base_change_percent": -2.32},
            {"symbol": "SUNPHARMA", "base_price": 1543.20, "base_change_percent": -2.17},
            {"symbol": "CIPLA", "base_price": 1398.60, "base_change_percent": -2.02},
            {"symbol": "DRREDDY", "base_price": 5432.75, "base_change_percent": -1.78},
            {"symbol": "DIVISLAB", "base_price": 3678.90, "base_change_percent": -1.66},
            {"symbol": "APOLLOHOSP", "base_price": 5789.45, "base_change_percent": -1.49},
            {"symbol": "TITAN", "base_price": 3234.60, "base_change_percent": -1.40},
        ],
    }

    def create_stock_data(stock_list):
        result = []
        for stock in stock_list:
            current_price = stock["base_price"]
            change_pct = stock["base_change_percent"]
            previous_price = current_price / (1 + change_pct / 100)
            change = current_price - previous_price

            result.append(
                {
                    "symbol": stock["symbol"],
                    "name": stock["symbol"],
                    "price": round(current_price, 2),
                    "change": round(change, 2),
                    "change_percent": round(change_pct, 2),
                    "volume": 10000000,
                    "high": round(current_price * 1.02, 2),
                    "low": round(current_price * 0.98, 2),
                }
            )
        return result

    return {
        "top_gainers": create_stock_data(stocks["gainers"]),
        "top_losers": create_stock_data(stocks["losers"]),
    }


def simulate_portfolio_data() -> dict:
    """Generate static portfolio data (no random variations)."""
    base_holdings = [
        {"tradingsymbol": "RELIANCE", "exchange": "NSE", "quantity": 50, "average_price": 2850.00, "base_last_price": 2934.65},
        {"tradingsymbol": "TCS", "exchange": "NSE", "quantity": 25, "average_price": 3650.00, "base_last_price": 3712.40},
        {"tradingsymbol": "INFY", "exchange": "NSE", "quantity": 30, "average_price": 1520.00, "base_last_price": 1587.30},
        {"tradingsymbol": "HDFCBANK", "exchange": "NSE", "quantity": 40, "average_price": 1680.00, "base_last_price": 1698.55},
        {"tradingsymbol": "ITC", "exchange": "NSE", "quantity": 100, "average_price": 445.00, "base_last_price": 456.75},
        {"tradingsymbol": "HINDUNILVR", "exchange": "NSE", "quantity": 15, "average_price": 2580.00, "base_last_price": 2654.35},
        {"tradingsymbol": "ICICIBANK", "exchange": "NSE", "quantity": 35, "average_price": 980.00, "base_last_price": 1024.80},
        {"tradingsymbol": "SBIN", "exchange": "NSE", "quantity": 80, "average_price": 620.00, "base_last_price": 643.15},
        {"tradingsymbol": "BAJFINANCE", "exchange": "NSE", "quantity": 8, "average_price": 6450.00, "base_last_price": 6789.30},
        {"tradingsymbol": "MARUTI", "exchange": "NSE", "quantity": 6, "average_price": 9850.00, "base_last_price": 10245.60},
        {"tradingsymbol": "ASIANPAINT", "exchange": "NSE", "quantity": 12, "average_price": 3180.00, "base_last_price": 3234.60},
        {"tradingsymbol": "LT", "exchange": "NSE", "quantity": 18, "average_price": 3320.00, "base_last_price": 3456.80},
        {"tradingsymbol": "KOTAKBANK", "exchange": "NSE", "quantity": 22, "average_price": 1780.00, "base_last_price": 1834.25},
    ]

    static_holdings = []
    total_investment = 0
    current_value = 0
    total_pnl = 0

    for holding in base_holdings:
        current_price = holding["base_last_price"]
        investment = holding["average_price"] * holding["quantity"]
        value = current_price * holding["quantity"]
        pnl = value - investment

        total_investment += investment
        current_value += value
        total_pnl += pnl

        static_holdings.append(
            {
                "tradingsymbol": holding["tradingsymbol"],
                "exchange": holding["exchange"],
                "quantity": holding["quantity"],
                "average_price": holding["average_price"],
                "last_price": round(current_price, 2),
                "pnl": round(pnl, 2),
                "day_change": 0,
                "day_change_percentage": 0,
                "instrument_token": 500000,
                "product": "CNC",
                "has_saved_analysis": False,
            }
        )

    pnl_percentage = (total_pnl / total_investment * 100) if total_investment > 0 else 0

    return {
        "holdings": static_holdings,
        "summary": {
            "total_holdings": len(static_holdings),
            "total_investment": round(total_investment, 2),
            "current_value": round(current_value, 2),
            "total_pnl": round(total_pnl, 2),
            "pnl_percentage": round(pnl_percentage, 2),
            "positions_count": len(static_holdings),
        },
    }
