from typing import TypedDict, Optional


class AgentResult(TypedDict):
    score: float
    explanation: str


class AnalysisState(TypedDict):
    # Inputs
    symbol: str
    access_token: str
    instrument_token: Optional[int]

    # LLM provider selection ("claude" | "openai" | None → openai default)
    llm_provider: Optional[str]

    # User ID for per-user BYOK key lookup
    user_id: Optional[int]

    # Agent outputs (each agent writes only its own key)
    stats_result: Optional[AgentResult]
    company_health_result: Optional[AgentResult]
    breaking_news_result: Optional[AgentResult]

    # Synthesizer output
    overall_score: Optional[float]
    verdict: Optional[str]
    risk_factors: Optional[list]    # Claude path: explicit downside risks
    conflict_summary: Optional[str] # Claude path: explanation when agents disagree

    # Metadata
    analyzed_at: Optional[str]
