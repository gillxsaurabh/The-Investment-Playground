from agents.registry import register_agent
from services.params import prompts as _prompts

SYSTEM_PROMPT = _prompts.get("general_chat")

# Self-register on import
register_agent(
    name="general_agent",
    description="Handles general trading questions, market education, and non-portfolio queries",
    tools=[],
)
