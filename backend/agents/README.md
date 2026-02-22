# Adding Agents to CogniCap

## Architecture

```
agents/
├── __init__.py          # Public API: run_agent(), clear_session()
├── state.py             # Shared AgentState (message history + context)
├── config.py            # LLM factory (Gemini 2.5 Flash)
├── supervisor.py        # Routes user messages to the right worker
├── registry.py          # Agent registry (auto-discovery)
├── tools/               # @tool-decorated functions agents can call
│   ├── portfolio_tools.py
│   ├── analysis_tools.py
│   └── market_tools.py
└── workers/             # One file per agent
    ├── portfolio_agent.py
    └── general_agent.py
```

The **supervisor** classifies each user message and routes it to the best worker agent. Workers are LangGraph ReAct agents that can call tools in a loop until they have an answer.

## Adding a New Agent

### Step 1: Create tools (if needed)

Add a new file in `agents/tools/`. Each tool is a plain function with the `@tool` decorator:

```python
# agents/tools/news_tools.py
from langchain_core.tools import tool

@tool
def search_stock_news(symbol: str) -> dict:
    """Search for recent news about a stock symbol."""
    # your implementation here
    return {"headlines": [...]}
```

Tools must have a **docstring** — the LLM reads it to decide when to call the tool.

### Step 2: Create the worker

Add a new file in `agents/workers/`. The only requirement is calling `register_agent()`:

```python
# agents/workers/news_agent.py
from agents.registry import register_agent
from agents.tools.news_tools import search_stock_news

register_agent(
    name="news_agent",
    description="Handles market news queries and event-driven analysis",
    tools=[search_stock_news],
)
```

- **name**: Unique identifier. The supervisor outputs this string to route messages.
- **description**: The supervisor reads this to decide which agent handles which queries. Be specific.
- **tools**: List of `@tool` functions this agent can call. Pass `[]` for a tool-less conversational agent.

### Step 3: Register the import

Add one import line in `agents/supervisor.py`:

```python
# Import workers to trigger self-registration
from agents.workers import portfolio_agent, general_agent  # noqa: F401
from agents.workers import news_agent  # noqa: F401  <-- add this
```

That's it. The supervisor automatically picks up the new agent, includes its description in the routing prompt, and wires the graph edges.

## Tool Guidelines

- Tools receive parameters from the LLM. If a tool needs `access_token`, include it as a parameter — the supervisor injects it via system message context.
- Wrap tool bodies in `try/except` and return `{"error": str(e)}` on failure so the agent can recover gracefully.
- Keep tool docstrings clear and concise — they directly affect how well the LLM chooses and uses the tool.
- Import heavy modules (like `stock_analyzer`) inside the function body to avoid slow startup.

## Testing an Agent

Start the backend and send a message that should route to your agent:

```bash
curl -X POST http://localhost:5000/api/chat/send \
  -H "Content-Type: application/json" \
  -d '{"message": "What is the latest news on RELIANCE?", "session_id": "test"}'
```

Check that `response` in the JSON output comes from your agent (you'll see tool call results in server logs if tools were invoked).
