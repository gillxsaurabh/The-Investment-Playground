from langchain_core.tools import tool
from broker import get_broker


@tool
def get_market_indices(access_token: str) -> dict:
    """Get current NIFTY 50 and SENSEX index values, including
    change and change percentage from the previous close."""
    try:
        broker = get_broker(access_token)
        quotes = broker.get_quote(["NSE:NIFTY 50", "BSE:SENSEX"])
        result = {}
        for key, name in [("NSE:NIFTY 50", "NIFTY 50"), ("BSE:SENSEX", "SENSEX")]:
            q = quotes.get(key, {})
            ohlc = q.get("ohlc", {})
            last = q.get("last_price", 0)
            open_p = ohlc.get("open", last)
            change = last - open_p
            result[name] = {
                "value": round(last, 2),
                "change": round(change, 2),
                "change_pct": round(
                    (change / open_p * 100) if open_p else 0, 2
                ),
            }
        return result
    except Exception as e:
        return {"error": str(e)}
