import os
import sys
from langchain_core.tools import tool

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))


@tool
def analyze_stock_health(access_token: str, symbol: str) -> dict:
    """Run a comprehensive health analysis on a specific stock using 3 specialist agents.
    Stats Agent checks technical indicators (ADX, EMA, relative strength).
    Company Health Agent checks fundamentals (ROE, D/E ratio, sales growth).
    Breaking News Agent assesses recent news sentiment.
    Returns an overall score from 1 to 5 with a verdict."""
    try:
        from agents.analysis_graph import analysis_graph

        result = analysis_graph.invoke({
            "symbol": symbol,
            "access_token": access_token,
            "instrument_token": None,
            "stats_result": None,
            "company_health_result": None,
            "breaking_news_result": None,
            "overall_score": None,
            "verdict": None,
            "analyzed_at": None,
        })

        return {
            "symbol": symbol,
            "overall_score": result.get("overall_score"),
            "verdict": result.get("verdict"),
            "agents": {
                "stats_agent": result.get("stats_result"),
                "company_health_agent": result.get("company_health_result"),
                "breaking_news_agent": result.get("breaking_news_result"),
            },
        }
    except Exception as e:
        return {"error": str(e), "symbol": symbol}
