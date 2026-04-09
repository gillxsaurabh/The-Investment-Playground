"""Fundamentals Analyst Agent — Fundamental analysis via Screener.in scraping.

Scrapes Screener.in for ROE, Debt/Equity and Sales Growth data, computes a
fundamental health score, then generates an LLM explanation.

Agent name: Fundamentals Analyst
Agent role: Assesses balance-sheet quality — ROE, D/E ratio and revenue growth
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from agents.config import get_llm
from agents.analysis_state import AnalysisState
from agents.shared.fundamentals_agent import scrape_fundamentals
from services.fundamentals import score_fundamentals


def company_health_agent_node(state: AnalysisState) -> dict:
    """Scrape fundamental data from Screener.in and generate Claude explanation."""
    symbol = state["symbol"]
    try:
        data = scrape_fundamentals(symbol)

        roe = data.get("roe")
        debt_to_equity = data.get("debt_to_equity")
        sales_growth = data.get("sales_growth")

        scored = score_fundamentals(roe=roe, debt_to_equity=debt_to_equity, sales_growth=sales_growth)
        score = scored.get("score", 3)
        summary = scored.get("summary", "Data unavailable")

        roe_str = f"{roe:.1f}%" if roe is not None else "N/A"
        de_str = f"{debt_to_equity:.2f}" if debt_to_equity is not None else "N/A"
        sg_str = f"{sales_growth:.1f}%" if sales_growth is not None else "N/A"
        raw_explanation = (
            f"Fundamentals from screener.in — ROE: {roe_str}, "
            f"Debt/Equity: {de_str}, Sales Growth: {sg_str}. Score: {score}/5."
        )

        # Generate explanation via Claude
        try:
            llm = get_llm(temperature=0.2, provider="claude", user_id=state.get("user_id"))
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
