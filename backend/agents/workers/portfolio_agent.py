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

SYSTEM_PROMPT = (
    "You are a portfolio analysis assistant for CogniCap, "
    "a trading portfolio dashboard connected to Zerodha Kite.\n\n"
    "You have access to the user's live portfolio data and analysis tools. "
    "When answering questions about holdings, P&L, or stock health, "
    "use the available tools to fetch real data rather than guessing.\n\n"
    "Always provide specific numbers when available. "
    "Format currency values in INR (₹)."
)

# Self-register on import
register_agent(
    name="portfolio_agent",
    description="Handles portfolio queries: holdings, P&L, stock analysis, market indices",
    tools=TOOLS,
)
