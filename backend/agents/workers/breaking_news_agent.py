"""Breaking News Agent — News sentiment analysis via Gemini LLM.

Uses an enhanced prompt to assess recent news, quarterly results,
regulatory developments, and sector-level events for a stock.
"""

from agents.config import get_llm
from agents.analysis_state import AnalysisState


def breaking_news_agent_node(state: AnalysisState) -> dict:
    """Analyze recent news sentiment via LLM and return score + explanation."""
    symbol = state["symbol"]
    try:
        llm = get_llm(temperature=0.3)
        prompt = (
            f"You are a financial news analyst specializing in Indian equity markets (NSE/BSE).\n\n"
            f"Analyze the stock **{symbol}** and assess its current news sentiment.\n\n"
            "Focus on:\n"
            "1. Recent quarterly earnings results and management guidance\n"
            "2. Major corporate actions (M&A, fundraising, restructuring, stake sales)\n"
            "3. Regulatory or governance concerns (SEBI actions, auditor flags, promoter pledging)\n"
            "4. Sector-level tailwinds or headwinds affecting this company\n"
            "5. Any breaking or material news from the last 30 days\n\n"
            "Provide your assessment in this EXACT format (no extra text before or after):\n"
            "SCORE: [integer 1-5]\n"
            "EXPLANATION: [3-4 sentences explaining what news/events you found, "
            "whether sentiment is positive/negative/mixed, and why you assigned this score. "
            "Be specific about which news items or developments informed your assessment.]\n\n"
            "Scoring guide:\n"
            "5 = Strong positive (earnings beat, major expansion, sector boom)\n"
            "4 = Positive outlook (steady growth, favorable policy changes)\n"
            "3 = Neutral/Mixed signals\n"
            "2 = Negative concerns (earnings miss, regulatory issues, management changes)\n"
            "1 = High risk (fraud allegations, severe debt crisis, bankruptcy concerns)"
        )

        response = llm.invoke(prompt)
        text = response.content.strip()

        # Parse structured response
        score = 3
        explanation = text

        if "SCORE:" in text and "EXPLANATION:" in text:
            lines = text.split("\n")
            for line in lines:
                stripped = line.strip()
                if stripped.startswith("SCORE:"):
                    try:
                        score = int(stripped.split(":")[1].strip())
                        score = max(1, min(5, score))
                    except (ValueError, IndexError):
                        score = 3
                elif stripped.startswith("EXPLANATION:"):
                    explanation = stripped.split(":", 1)[1].strip()
                    # Capture any continuation lines
                    idx = lines.index(line)
                    for cont_line in lines[idx + 1:]:
                        cont = cont_line.strip()
                        if cont and not cont.startswith("SCORE:"):
                            explanation += " " + cont

        return {"breaking_news_result": {"score": float(score), "explanation": explanation}}

    except Exception as e:
        error_msg = str(e)
        print(f"Breaking News Agent error for {symbol}: {error_msg}")
        explanation = f"News sentiment analysis could not be completed for {symbol}: {error_msg}"
        return {"breaking_news_result": {"score": 3.0, "explanation": explanation}}
