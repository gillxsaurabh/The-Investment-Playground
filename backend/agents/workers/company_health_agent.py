"""Fundamentals Analyst Agent — Fundamental analysis via Screener.in scraping.

Scrapes Screener.in for ROE, Debt/Equity and Sales Growth data, computes a
fundamental health score, then generates an LLM explanation.

Agent name: Fundamentals Analyst
Agent role: Assesses balance-sheet quality — ROE, D/E ratio and revenue growth
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from stock_analyzer import StockAnalyzer
from agents.config import get_llm
from agents.analysis_state import AnalysisState


def company_health_agent_node(state: AnalysisState) -> dict:
    """Scrape fundamental data and generate LLM explanation."""
    symbol = state["symbol"]
    try:
        # StockAnalyzer for scraping only — no Kite instance needed
        analyzer = StockAnalyzer(kite_instance=None, gemini_api_key=None)
        fundamentals = analyzer._calculate_fundamental_score(symbol)

        score = fundamentals.get("score", 3)
        roe = fundamentals.get("roe")
        debt_to_equity = fundamentals.get("debt_to_equity")
        sales_growth = fundamentals.get("sales_growth")
        summary = fundamentals.get("summary", "Data unavailable")

        # Build a raw data explanation as fallback
        roe_str = f'{roe:.1f}%' if roe is not None else 'N/A'
        de_str = f'{debt_to_equity:.2f}' if debt_to_equity is not None else 'N/A'
        sg_str = f'{sales_growth:.1f}%' if sales_growth is not None else 'N/A'
        raw_explanation = (
            f"Fundamentals from screener.in — ROE: {roe_str}, "
            f"Debt/Equity: {de_str}, Sales Growth: {sg_str}. Score: {score}/5."
        )

        # Generate explanation via LLM (best-effort)
        provider = state.get("llm_provider")
        try:
            llm = get_llm(temperature=0.2, provider=provider)
            if provider == "claude":
                prompt = (
                    f"You are a fundamental analysis expert specializing in Indian listed companies.\n\n"
                    f"Given these data points for {symbol} from screener.in/company/{symbol}/consolidated/:\n\n"
                    f"- ROE (Return on Equity): {roe_str}\n"
                    f"- Debt/Equity ratio: {de_str}\n"
                    f"- Sales Growth: {sg_str}\n"
                    f"- Computed fundamental score: {score}/5\n\n"
                    "Write 2-3 sentences covering: (1) whether the balance sheet quality is good, average, or poor "
                    "with specific thresholds (ROE>15%, D/E<1), (2) the earnings quality and growth trajectory, "
                    "(3) the key fundamental risk that could threaten the investment thesis."
                )
            else:
                prompt = (
                    f"You are a fundamental analysis expert. Given these data points for {symbol} "
                    f"scraped from screener.in/company/{symbol}/consolidated/:\n\n"
                    f"- ROE (Return on Equity): {roe_str}\n"
                    f"- Debt/Equity ratio: {de_str}\n"
                    f"- Sales Growth: {sg_str}\n"
                    f"- Computed score: {score}/5\n\n"
                    "Write a 2-3 sentence explanation of what these fundamentals indicate about "
                    "the company's financial health. Mention the data source. "
                    "Explain the scoring logic (e.g., ROE > 15% with D/E < 1 is excellent)."
                )
            response = llm.invoke(prompt)
            explanation = response.content.strip()
        except Exception as llm_err:
            print(f"Company Health Agent LLM error for {symbol}: {llm_err}")
            explanation = raw_explanation

        return {"company_health_result": {"score": float(score), "explanation": explanation}}

    except Exception as e:
        error_msg = str(e)
        print(f"Company Health Agent error for {symbol}: {error_msg}")
        explanation = f"Fundamental analysis could not be completed for {symbol}: {error_msg}"
        return {"company_health_result": {"score": 3.0, "explanation": explanation}}
