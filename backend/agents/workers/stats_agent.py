"""Stats Agent — Technical analysis (Recency + Trend).

Reuses StockAnalyzer methods for Kite API data fetching and indicator computation.
Uses LLM to generate a rich text explanation of the results.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from broker import get_broker
from stock_analyzer import StockAnalyzer
from agents.config import get_llm
from agents.analysis_state import AnalysisState


def stats_agent_node(state: AnalysisState) -> dict:
    """Compute recency + trend scores, then generate LLM explanation."""
    symbol = state["symbol"]
    try:
        broker = get_broker(state["access_token"])
        analyzer = StockAnalyzer(kite_instance=broker.raw_kite, gemini_api_key=None)

        # Fetch data
        nifty_data = analyzer._get_nifty_data()
        instrument_token = state.get("instrument_token")
        if not instrument_token:
            instrument_token = analyzer._get_instrument_token(symbol)
        stock_data = analyzer._fetch_stock_history(instrument_token, symbol)

        if stock_data is None or stock_data.empty:
            return {"stats_result": {"score": 3.0, "explanation": f"Insufficient historical data available for {symbol} to perform technical analysis."}}

        # Calculate technical scores (reuses existing logic)
        technical = analyzer._calculate_technical_score(stock_data, nifty_data, symbol)

        recency = technical.get("recency", {})
        trend = technical.get("trend", {})
        recency_score = recency.get("score", 3)
        trend_score = trend.get("score", 3)
        stats_score = round((recency_score * 0.5 + trend_score * 0.5), 1)

        # Build a raw data explanation as fallback
        raw_explanation = (
            f"Recency (Relative Strength vs Nifty): {recency_score}/5 — {recency.get('detail', 'N/A')}. "
            f"Trend (ADX + EMA): {trend_score}/5 — Strength: {trend.get('strength', 'N/A')}, "
            f"Direction: {trend.get('direction', 'N/A')}."
        )

        # Generate explanation via LLM (best-effort)
        try:
            llm = get_llm(temperature=0.2)
            prompt = (
                f"You are a technical analysis expert. Given these results for {symbol}:\n\n"
                f"- Recency (Relative Strength vs Nifty 50, last 90 days): {recency_score}/5 — {recency.get('detail', 'N/A')}\n"
                f"- Trend (ADX + EMA crossover): {trend_score}/5 — Strength: {trend.get('strength', 'N/A')}, Direction: {trend.get('direction', 'N/A')}\n"
                f"- Combined stats score: {stats_score}/5\n\n"
                "Write a 2-3 sentence explanation of what these technical indicators mean for this stock. "
                "Be specific with numbers. Explain what was checked and how the score was derived."
            )
            response = llm.invoke(prompt)
            explanation = response.content.strip()
        except Exception as llm_err:
            print(f"Stats Agent LLM error for {symbol}: {llm_err}")
            explanation = raw_explanation

        return {"stats_result": {"score": stats_score, "explanation": explanation}}

    except Exception as e:
        error_msg = str(e)
        print(f"Stats Agent error for {symbol}: {error_msg}")
        explanation = f"Technical analysis could not be completed for {symbol}: {error_msg}"
        return {"stats_result": {"score": 3.0, "explanation": explanation}}
