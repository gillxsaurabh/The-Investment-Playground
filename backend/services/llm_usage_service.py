"""LLM usage tracking — fire-and-forget INSERT after each LLM call.

Never raises — usage tracking must never break the caller.
"""

import logging
from typing import Optional

logger = logging.getLogger(__name__)

# Cost per million tokens (input / output) by provider+model
_COST_MAP: dict[str, tuple[float, float]] = {
    # (input_cost_per_M, output_cost_per_M)
    "anthropic:claude-sonnet-4-6": (3.0, 15.0),
    "openai:gpt-4o-mini": (0.15, 0.60),
}


def _estimate_cost(provider: str, model: str, input_tokens: int, output_tokens: int) -> float:
    key = f"{provider}:{model}"
    rates = _COST_MAP.get(key, (0.0, 0.0))
    return round(
        (input_tokens / 1_000_000) * rates[0] + (output_tokens / 1_000_000) * rates[1],
        8,
    )


def record_usage(
    pipeline: str,
    provider: str,
    model: str,
    input_tokens: int,
    output_tokens: int,
    user_id: Optional[int] = None,
) -> None:
    """Insert a row into llm_usage. Silent on any error."""
    try:
        cost = _estimate_cost(provider, model, input_tokens, output_tokens)
        from services.db import get_conn
        conn = get_conn()
        try:
            conn.execute(
                "INSERT INTO llm_usage "
                "(user_id, pipeline, provider, model, input_tokens, output_tokens, cost_usd) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (user_id, pipeline, provider, model, input_tokens, output_tokens, cost),
            )
            conn.commit()
        finally:
            conn.close()
    except Exception as exc:
        logger.warning("[LLMUsage] Failed to record usage: %s", exc)


def get_usage_summary(
    user_id: Optional[int] = None,
    pipeline: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> list[dict]:
    """Return aggregated usage grouped by pipeline/provider/model.

    All date strings should be ISO format ('YYYY-MM-DD' or 'YYYY-MM-DD HH:MM:SS').
    """
    from services.db import get_conn
    conn = get_conn()
    try:
        wheres = []
        params: list = []
        if user_id is not None:
            wheres.append("user_id = ?")
            params.append(user_id)
        if pipeline:
            wheres.append("pipeline = ?")
            params.append(pipeline)
        if start_date:
            wheres.append("created_at >= ?")
            params.append(start_date)
        if end_date:
            wheres.append("created_at <= ?")
            params.append(end_date)

        where_clause = ("WHERE " + " AND ".join(wheres)) if wheres else ""
        rows = conn.execute(
            f"""
            SELECT pipeline, provider, model,
                   COUNT(*) AS calls,
                   SUM(input_tokens)  AS total_input_tokens,
                   SUM(output_tokens) AS total_output_tokens,
                   ROUND(SUM(cost_usd), 6) AS total_cost_usd
            FROM llm_usage
            {where_clause}
            GROUP BY pipeline, provider, model
            ORDER BY total_cost_usd DESC
            """,
            params,
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()
