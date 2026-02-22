from langchain_core.tools import tool
from broker import get_broker


@tool
def get_portfolio_holdings(access_token: str) -> dict:
    """Fetch the user's current portfolio holdings from Zerodha Kite.
    Returns a list of holdings with symbol, quantity, average price,
    last price, and P&L for each stock."""
    try:
        broker = get_broker(access_token)
        holdings = broker.get_holdings()
        result = []
        for h in holdings:
            result.append({
                "symbol": h["tradingsymbol"],
                "quantity": h["quantity"],
                "avg_price": h["average_price"],
                "last_price": h["last_price"],
                "pnl": h["pnl"],
            })
        return {"holdings": result, "count": len(result)}
    except Exception as e:
        return {"error": str(e)}


@tool
def get_portfolio_summary(access_token: str) -> dict:
    """Get a high-level summary of the user's portfolio including
    total investment, current value, and overall P&L."""
    try:
        broker = get_broker(access_token)
        holdings = broker.get_holdings()
        total_investment = sum(h["average_price"] * h["quantity"] for h in holdings)
        current_value = sum(h["last_price"] * h["quantity"] for h in holdings)
        total_pnl = sum(h["pnl"] for h in holdings)
        return {
            "total_investment": round(total_investment, 2),
            "current_value": round(current_value, 2),
            "total_pnl": round(total_pnl, 2),
            "pnl_percentage": round(
                (total_pnl / total_investment * 100) if total_investment > 0 else 0, 2
            ),
            "holdings_count": len(holdings),
        }
    except Exception as e:
        return {"error": str(e)}
