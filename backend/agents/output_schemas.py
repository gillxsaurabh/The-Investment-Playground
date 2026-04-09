"""Pydantic v2 schemas for validating LLM JSON output.

Used in the buy and sell pipelines to validate per-item LLM responses before
they are merged back into the stock/holding dicts.

Validation is applied per-item so a single malformed entry doesn't discard the
whole batch — failed items fall back to clamped defaults.
"""

from typing import Literal, Optional

from pydantic import BaseModel, Field


class ConvictionScore(BaseModel):
    """Per-stock output from ai_rank_stocks (Agent 5 — AI Conviction Engine)."""

    symbol: str
    conviction_score: int = Field(ge=1, le=10)
    reason: str = Field(max_length=300, default="")
    primary_risk: Optional[str] = Field(default=None, max_length=300)
    trade_type: Optional[Literal["pullback_entry", "momentum_breakout", "accumulate_dip"]] = None
    news_sentiment: int = Field(ge=1, le=5, default=3)
    news_flag: Literal["warning", "clear"] = "clear"


class SellAnalysis(BaseModel):
    """Per-holding output from ai_rank_sell_candidates (Sell Signal Engine)."""

    symbol: str
    sell_conviction: int = Field(ge=1, le=10)
    sell_reason: str = Field(max_length=300, default="")
    hold_reason: str = Field(max_length=300, default="")
    news_sentiment: int = Field(ge=1, le=5, default=3)
    news_flag: Literal["warning", "clear"] = "clear"


class PortfolioRank(BaseModel):
    """Per-stock output from rank_final_shortlist (Portfolio Ranker)."""

    symbol: str
    rank_reason: str = Field(max_length=300, default="")
    portfolio_note: Literal["diversified", "sector_concentration_risk", "correlated_with_rank_1"] = "diversified"
