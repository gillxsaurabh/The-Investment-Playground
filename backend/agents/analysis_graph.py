"""Scatter-gather analysis graph.

Runs 3 specialist agents in parallel, then a synthesizer combines
their outputs into an overall score and verdict.

    START ──┬──> stats_agent ──────────┐
            ├──> company_health_agent ──┤──> synthesizer ──> END
            └──> breaking_news_agent ──┘
"""

import json as json_lib
from datetime import datetime

from langgraph.graph import StateGraph, START, END

from agents.analysis_state import AnalysisState
from agents.config import get_llm
from agents.workers.stats_agent import stats_agent_node
from agents.workers.company_health_agent import company_health_agent_node
from agents.workers.breaking_news_agent import breaking_news_agent_node
from constants import CLAUDE_SYNTHESIS_THINKING_BUDGET


def _synthesizer_node(state: AnalysisState) -> dict:
    """Combine 3 agent outputs into an overall score and action verdict."""
    stats = state.get("stats_result") or {"score": 3.0, "explanation": "Not available"}
    health = state.get("company_health_result") or {"score": 3.0, "explanation": "Not available"}
    news = state.get("breaking_news_result") or {"score": 3.0, "explanation": "Not available"}
    symbol = state["symbol"]
    provider = state.get("llm_provider")

    # Fallback: average of agent scores
    overall_score = round((stats["score"] + health["score"] + news["score"]) / 3, 1)
    verdict = f"Analysis complete for {symbol}."
    risk_factors = None
    conflict_summary = None

    # Detect signal conflict: score spread >= 1.5 triggers explicit conflict resolution
    scores = [stats["score"], health["score"], news["score"]]
    conflict_detected = (max(scores) - min(scores)) >= 1.5

    # Collect risk flags from Claude news agent (may be empty on Gemini path)
    news_risk_flags = news.get("risk_flags", [])

    try:
        if provider == "claude":
            llm = get_llm(
                temperature=0.1,
                provider="claude",
                extended_thinking=True,
                thinking_budget=CLAUDE_SYNTHESIS_THINKING_BUDGET,
            )

            conflict_instruction = ""
            if conflict_detected:
                conflict_instruction = (
                    f"\n\nIMPORTANT: The agents disagree significantly (spread of "
                    f"{max(scores) - min(scores):.1f} points). Explain which signal dominates "
                    "and why in the conflict_summary field."
                )

            risk_flags_str = ""
            if news_risk_flags:
                risk_flags_str = f"\nNews risk flags from sentiment agent: {', '.join(news_risk_flags)}"

            prompt = (
                f"You are a senior investment analyst. Three specialist agents have analyzed {symbol}:{conflict_instruction}\n\n"
                f"**Quantitative Analyst** (Technical/Momentum): {stats['score']}/5\n{stats['explanation']}\n\n"
                f"**Fundamentals Analyst** (Balance Sheet): {health['score']}/5\n{health['explanation']}\n\n"
                f"**News Sentinel** (Sentiment/Events): {news['score']}/5\n{news['explanation']}"
                f"{risk_flags_str}\n\n"
                "Synthesize all three signals and return a JSON object with exactly these keys:\n\n"
                "{\n"
                '  "overall_score": <float 1.0-5.0, one decimal>,\n'
                '  "verdict": "<action> — <1-2 sentence reasoning>",\n'
                '  "risk_factors": ["<most important downside risk>", "<second risk>"],\n'
                '  "conflict_summary": "<explanation of why one signal dominates, or null if agents agree>",\n'
                '  "confidence": "high" | "medium" | "low"\n'
                "}\n\n"
                "Actions: Strong Buy, Buy, Accumulate, Hold, Reduce, Exit\n\n"
                "Return ONLY the JSON object, no additional text or markdown."
            )

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
                raw_score = parsed.get("overall_score", overall_score)
                overall_score = round(max(1.0, min(5.0, float(raw_score))), 1)
                verdict = parsed.get("verdict", verdict)
                risk_factors = parsed.get("risk_factors") or []
                conflict_summary = parsed.get("conflict_summary") or (
                    None if not conflict_detected else "Agents disagree — see individual scores."
                )
            except (json_lib.JSONDecodeError, ValueError) as parse_err:
                print(f"Synthesizer JSON parse error for {symbol}: {parse_err}")
                # overall_score fallback already set above

        else:
            # Gemini path — original SCORE:/VERDICT: format unchanged
            llm = get_llm(temperature=0.1)
            prompt = (
                f"You are a senior stock analysis supervisor. Three specialist agents have analyzed {symbol}:\n\n"
                f"**Stats Agent** (Technical Analysis): {stats['score']}/5\n{stats['explanation']}\n\n"
                f"**Company Health Agent** (Fundamentals): {health['score']}/5\n{health['explanation']}\n\n"
                f"**Breaking News Agent** (Sentiment): {news['score']}/5\n{news['explanation']}\n\n"
                "Based on ALL three assessments, provide:\n"
                "1. An overall score (1-5, to one decimal place) as a weighted synthesis\n"
                "2. A concise action recommendation with 1-2 sentences of reasoning\n\n"
                "Use this EXACT format:\n"
                "SCORE: [number]\n"
                "VERDICT: [action] — [reasoning]\n\n"
                "Actions: Strong Buy, Buy, Accumulate, Hold, Reduce, Exit\n"
            )

            response = llm.invoke(prompt)
            text = response.content.strip()

            if "SCORE:" in text and "VERDICT:" in text:
                lines = text.split("\n")
                for line in lines:
                    stripped = line.strip()
                    if stripped.startswith("SCORE:"):
                        try:
                            parsed_score = float(stripped.split(":")[1].strip())
                            overall_score = round(max(1.0, min(5.0, parsed_score)), 1)
                        except (ValueError, IndexError):
                            pass
                    elif stripped.startswith("VERDICT:"):
                        verdict = stripped.split(":", 1)[1].strip()
                        idx = lines.index(line)
                        for cont_line in lines[idx + 1:]:
                            cont = cont_line.strip()
                            if cont and not cont.startswith("SCORE:"):
                                verdict += " " + cont

    except Exception as e:
        error_msg = str(e)
        print(f"Synthesizer error for {symbol}: {error_msg}")
        if "RESOURCE_EXHAUSTED" in error_msg or "429" in error_msg or "rate" in error_msg.lower() or "quota" in error_msg.lower():
            verdict = "Hold — AI verdict unavailable due to rate limits. Score is an average of agent scores. Please try again later."
        else:
            verdict = "Hold — AI verdict unavailable. Score is an average of agent scores."

    return {
        "overall_score": overall_score,
        "verdict": verdict,
        "risk_factors": risk_factors,
        "conflict_summary": conflict_summary,
        "analyzed_at": datetime.now().isoformat(),
    }


def build_analysis_graph():
    """Build and compile the scatter-gather analysis graph."""
    graph = StateGraph(AnalysisState)

    # Agent nodes
    graph.add_node("stats_agent", stats_agent_node)
    graph.add_node("company_health_agent", company_health_agent_node)
    graph.add_node("breaking_news_agent", breaking_news_agent_node)
    graph.add_node("synthesizer", _synthesizer_node)

    # Fan-out: START -> all 3 agents in parallel
    graph.add_edge(START, "stats_agent")
    graph.add_edge(START, "company_health_agent")
    graph.add_edge(START, "breaking_news_agent")

    # Fan-in: all 3 agents -> synthesizer
    graph.add_edge("stats_agent", "synthesizer")
    graph.add_edge("company_health_agent", "synthesizer")
    graph.add_edge("breaking_news_agent", "synthesizer")

    # synthesizer -> END
    graph.add_edge("synthesizer", END)

    return graph.compile()


# Compiled graph singleton
analysis_graph = build_analysis_graph()
