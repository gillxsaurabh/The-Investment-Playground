"""Scatter-gather analysis graph.

Runs 3 specialist agents in parallel, then a synthesizer combines
their outputs into an overall score and verdict.

    START ──┬──> stats_agent ──────────┐
            ├──> company_health_agent ──┤──> synthesizer ──> END
            └──> breaking_news_agent ──┘
"""

from datetime import datetime

from langgraph.graph import StateGraph, START, END

from agents.analysis_state import AnalysisState
from agents.config import get_llm
from agents.workers.stats_agent import stats_agent_node
from agents.workers.company_health_agent import company_health_agent_node
from agents.workers.breaking_news_agent import breaking_news_agent_node


def _synthesizer_node(state: AnalysisState) -> dict:
    """Combine 3 agent outputs into an overall score and action verdict."""
    stats = state.get("stats_result") or {"score": 3.0, "explanation": "Not available"}
    health = state.get("company_health_result") or {"score": 3.0, "explanation": "Not available"}
    news = state.get("breaking_news_result") or {"score": 3.0, "explanation": "Not available"}
    symbol = state["symbol"]

    # Fallback: average of agent scores
    overall_score = round((stats["score"] + health["score"] + news["score"]) / 3, 1)
    verdict = f"Analysis complete for {symbol}."

    try:
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
                        parsed = float(stripped.split(":")[1].strip())
                        overall_score = round(max(1.0, min(5.0, parsed)), 1)
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
            verdict = f"Hold — AI verdict unavailable due to rate limits. Score is an average of agent scores. Please try again later."
        else:
            verdict = f"Hold — AI verdict unavailable. Score is an average of agent scores."

    return {
        "overall_score": overall_score,
        "verdict": verdict,
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
