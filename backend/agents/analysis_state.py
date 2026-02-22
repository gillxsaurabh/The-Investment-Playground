from typing import TypedDict, Optional


class AgentResult(TypedDict):
    score: float
    explanation: str


class AnalysisState(TypedDict):
    # Inputs
    symbol: str
    access_token: str
    instrument_token: Optional[int]

    # Agent outputs (each agent writes only its own key)
    stats_result: Optional[AgentResult]
    company_health_result: Optional[AgentResult]
    breaking_news_result: Optional[AgentResult]

    # Synthesizer output
    overall_score: Optional[float]
    verdict: Optional[str]

    # Metadata
    analyzed_at: Optional[str]
