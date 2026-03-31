from langgraph.graph import StateGraph, START, END
from langgraph.prebuilt import create_react_agent
from langchain_core.messages import SystemMessage

from agents.state import AgentState
from agents.config import get_llm
from agents.registry import get_registered_agents, get_agent_descriptions

# Import workers to trigger self-registration
from agents.workers import portfolio_agent, general_agent  # noqa: F401


def _supervisor_node(state: AgentState) -> dict:
    """Classify user intent and pick the right worker agent.

    Uses OpenAI (GPT-4o-mini) for routing — it's fast, cheap, and well-suited
    for classification tasks.  Claude is reserved for financial analysis.
    Falls back to Gemini if OPENAI_API_KEY is not set.
    """
    llm = get_llm(temperature=0, provider="openai", user_id=state.get("user_id"))
    agent_descriptions = get_agent_descriptions()
    agent_names = list(get_registered_agents().keys())

    system_msg = SystemMessage(content=(
        "You are a routing supervisor. "
        "Analyze the user's message and decide which specialist agent should handle it.\n\n"
        f"Available agents:\n{agent_descriptions}\n\n"
        f"Respond with ONLY the agent name (one of: {', '.join(agent_names)}), nothing else. "
        "If unsure, respond with 'general_agent'."
    ))

    messages = [system_msg, state["messages"][-1]]
    response = llm.invoke(messages)

    chosen = response.content.strip().lower()
    if chosen not in agent_names:
        chosen = "general_agent"

    return {"next_agent": chosen}


def _route_to_agent(state: AgentState) -> str:
    """Conditional edge: return the chosen worker name."""
    return state.get("next_agent", "general_agent")


def _make_worker_node(description: str, tools: list):
    """Build a worker node function backed by a ReAct agent."""
    system_prompt = (
        f"You are a CogniCap specialist: {description}\n\n"
        "When the user's access_token is provided in the conversation context, "
        "always pass it to tools that require it."
    )

    def worker(state: AgentState) -> dict:
        # LLM is instantiated per-request so per-user BYOK keys are resolved correctly
        agent = create_react_agent(
            model=get_llm(user_id=state.get("user_id")),
            tools=tools,
            prompt=system_prompt,
        )

        # Inject access token context if available
        messages = list(state["messages"])
        access_token = state.get("access_token")
        if access_token:
            context_msg = SystemMessage(
                content=f"The user's access_token is: {access_token}. "
                "Pass this value to any tool that requires an access_token parameter."
            )
            messages = [context_msg] + messages

        result = agent.invoke({"messages": messages})
        # Return only new messages (skip the input messages we passed)
        return {"messages": result["messages"][len(messages):]}

    return worker


def build_graph():
    """Build and compile the supervisor-worker graph."""
    graph = StateGraph(AgentState)

    # Supervisor node
    graph.add_node("supervisor", _supervisor_node)

    # Worker nodes from registry
    registered = get_registered_agents()
    for name, (description, tools) in registered.items():
        graph.add_node(name, _make_worker_node(description, tools))

    # Edges
    graph.add_edge(START, "supervisor")
    graph.add_conditional_edges(
        "supervisor",
        _route_to_agent,
        {name: name for name in registered.keys()},
    )
    for name in registered.keys():
        graph.add_edge(name, END)

    return graph.compile()


# Graph is built lazily on first use — see agents/__init__.py
