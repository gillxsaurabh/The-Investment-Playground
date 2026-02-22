from agents.supervisor import app_graph
from langchain_core.messages import HumanMessage

# Per-session conversation history
_graph_sessions: dict[str, list] = {}


def run_agent(message: str, session_id: str, access_token: str = None) -> str:
    """Run the agent graph with a user message.

    This is the single entry point called by Flask routes.
    Maintains conversation history per session_id.

    Returns the assistant's text response.
    """
    if session_id not in _graph_sessions:
        _graph_sessions[session_id] = []

    history = _graph_sessions[session_id]
    history.append(HumanMessage(content=message))

    result = app_graph.invoke({
        "messages": list(history),
        "access_token": access_token,
        "session_id": session_id,
        "next_agent": None,
    })

    output_messages = result["messages"]
    ai_response = output_messages[-1].content

    # Persist the full message history for the session
    _graph_sessions[session_id] = output_messages

    return ai_response


def clear_session(session_id: str):
    """Clear a chat session's history."""
    _graph_sessions.pop(session_id, None)
