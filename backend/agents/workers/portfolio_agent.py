from agents.registry import register_agent
from agents.tools.portfolio_tools import get_portfolio_holdings, get_portfolio_summary
from agents.tools.analysis_tools import analyze_stock_health
from agents.tools.market_tools import get_market_indices

TOOLS = [
    get_portfolio_holdings,
    get_portfolio_summary,
    analyze_stock_health,
    get_market_indices,
]

from services.params import prompts as _prompts

SYSTEM_PROMPT = _prompts.get("portfolio_chat")

# Self-register on import
register_agent(
    name="portfolio_agent",
    description="Handles portfolio queries: holdings, P&L, stock analysis, market indices",
    tools=TOOLS,
)
