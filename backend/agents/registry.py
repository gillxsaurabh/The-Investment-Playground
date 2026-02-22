from typing import Dict, List, Tuple
from langchain_core.tools import BaseTool

# Registry: name -> (description, tools_list)
_agent_registry: Dict[str, Tuple[str, List[BaseTool]]] = {}


def register_agent(name: str, description: str, tools: List[BaseTool]):
    """Register a worker agent with its name, description, and tools.

    The supervisor uses the description to decide which agent to route to.
    The tools are bound to a ReAct agent at graph build time.
    """
    _agent_registry[name] = (description, tools)


def get_registered_agents() -> Dict[str, Tuple[str, List[BaseTool]]]:
    """Return all registered agents."""
    return _agent_registry.copy()


def get_agent_descriptions() -> str:
    """Format agent descriptions for the supervisor routing prompt."""
    lines = []
    for name, (desc, _) in _agent_registry.items():
        lines.append(f"- {name}: {desc}")
    return "\n".join(lines)
