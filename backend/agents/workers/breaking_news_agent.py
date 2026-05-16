"""News Sentinel Agent — News sentiment analysis via Claude AI.

Uses an enhanced prompt to assess recent quarterly results, corporate actions,
regulatory developments, and sector-level events, then scores sentiment 1-5.

Returns structured JSON with key_events, risk_flags, sentiment_direction,
and time_horizon_risk — used by the synthesizer for conflict detection.

Agent name: News Sentinel
Agent role: Scans recent news, earnings events and regulatory flags to assess sentiment risk
"""

import json as json_lib

from agents.config import get_llm
from agents.analysis_state import AnalysisState


def breaking_news_agent_node(state: AnalysisState) -> dict:
    """Analyze recent news sentiment via Claude and return score + explanation."""
    symbol = state["symbol"]
    try:
        from services.params import prompts as _prompts
        llm = get_llm(temperature=0.3, provider="claude", user_id=state.get("user_id"))
        prompt = _prompts.render("news_sentinel", symbol=symbol)

        response = llm.invoke(prompt)
        text = response.content.strip()

        # Strip markdown fences if present
        if text.startswith("```"):
            parts = text.split("```")
            text = parts[1] if len(parts) > 1 else text
            if text.startswith("json"):
                text = text[4:]
            text = text.strip()

        try:
            parsed = json_lib.loads(text)
            score = max(1, min(5, int(parsed.get("score", 3))))
            result = {
                "score": float(score),
                "explanation": parsed.get("explanation", text),
                "key_events": parsed.get("key_events", []),
                "risk_flags": parsed.get("risk_flags", []),
                "sentiment_direction": parsed.get("sentiment_direction", "neutral"),
                "time_horizon_risk": parsed.get("time_horizon_risk", "none"),
            }
        except (json_lib.JSONDecodeError, ValueError):
            # JSON parse failed — fall back to raw text
            result = {"score": 3.0, "explanation": text}

        return {"breaking_news_result": result}

    except Exception as e:
        error_msg = str(e)
        print(f"Breaking News Agent error for {symbol}: {error_msg}")
        explanation = f"News sentiment analysis could not be completed for {symbol}: {error_msg}"
        return {"breaking_news_result": {"score": 3.0, "explanation": explanation}}
