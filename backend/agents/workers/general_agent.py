from agents.registry import register_agent

SYSTEM_PROMPT = (
    "You are CogniCap's general assistant. You help with "
    "general trading knowledge, market concepts, and financial education.\n\n"
    "You do not have access to the user's portfolio data. "
    "If the user asks about their specific holdings or portfolio, "
    "let them know you'll route their question to the portfolio specialist."
)

# Self-register on import
register_agent(
    name="general_agent",
    description="Handles general trading questions, market education, and non-portfolio queries",
    tools=[],
)
