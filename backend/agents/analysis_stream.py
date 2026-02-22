"""Sequential analysis runner that yields SSE events.

Runs agents one at a time so the frontend can show real-time progress
per agent. Yields Server-Sent Events as each agent starts/completes.
Each agent is isolated — if one fails, the rest still run.
"""

import json
from datetime import datetime

from agents.analysis_state import AnalysisState
from agents.workers.stats_agent import stats_agent_node
from agents.workers.company_health_agent import company_health_agent_node
from agents.workers.breaking_news_agent import breaking_news_agent_node
from agents.analysis_graph import _synthesizer_node


def _sse(event: str, data: dict) -> str:
    """Format a Server-Sent Event string.

    Each event ends with two newlines (SSE spec) plus a comment line
    that acts as flush padding — this prevents proxy/transport buffering.
    """
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


def run_analysis_stream(symbol: str, access_token: str, instrument_token: int | None = None):
    """Generator yielding SSE events as each agent completes.

    Agents run sequentially: stats → company_health → breaking_news → synthesizer.
    Each agent is wrapped in try/except so failures don't stop the pipeline.
    """
    state: AnalysisState = {
        "symbol": symbol,
        "access_token": access_token,
        "instrument_token": instrument_token,
        "stats_result": None,
        "company_health_result": None,
        "breaking_news_result": None,
        "overall_score": None,
        "verdict": None,
        "analyzed_at": None,
    }

    agents = [
        ("stats_agent", stats_agent_node, "stats_result"),
        ("company_health_agent", company_health_agent_node, "company_health_result"),
        ("breaking_news_agent", breaking_news_agent_node, "breaking_news_result"),
    ]

    for name, node_fn, result_key in agents:
        print(f"[SSE] {symbol}: yielding agent_start for {name}")
        yield _sse("agent_start", {"agent": name})

        try:
            result = node_fn(state)
            state.update(result)
            agent_result = state.get(result_key)
        except Exception as e:
            print(f"Stream: {name} failed for {symbol}: {e}")
            agent_result = {"score": 3.0, "explanation": f"{name} failed: {str(e)}"}
            state[result_key] = agent_result

        print(f"[SSE] {symbol}: yielding agent_complete for {name}")
        yield _sse("agent_complete", {"agent": name, "result": agent_result})

    # Synthesizer
    print(f"[SSE] {symbol}: yielding agent_start for synthesizer")
    yield _sse("agent_start", {"agent": "synthesizer"})
    try:
        synth = _synthesizer_node(state)
        state.update(synth)
    except Exception as e:
        print(f"Stream: synthesizer failed for {symbol}: {e}")
        scores = []
        for key in ["stats_result", "company_health_result", "breaking_news_result"]:
            r = state.get(key)
            if r and isinstance(r, dict):
                scores.append(r.get("score", 3.0))
        overall = round(sum(scores) / len(scores), 1) if scores else 3.0
        state["overall_score"] = overall
        state["verdict"] = f"Hold — AI verdict unavailable. Score is average of {len(scores)} agent(s)."
        state["analyzed_at"] = datetime.now().isoformat()

    # Final complete event with full response
    final = {
        "success": True,
        "symbol": symbol,
        "overall_score": state.get("overall_score"),
        "verdict": state.get("verdict"),
        "agents": {
            "stats_agent": state.get("stats_result"),
            "company_health_agent": state.get("company_health_result"),
            "breaking_news_agent": state.get("breaking_news_result"),
        },
        "analyzed_at": state.get("analyzed_at"),
    }
    print(f"[SSE] {symbol}: yielding complete event")
    yield _sse("complete", final)
