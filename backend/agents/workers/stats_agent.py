"""Quantitative Analyst Agent — Technical analysis (Recency + Trend).

Computes relative-strength recency scores and ADX/EMA trend scores for a single stock
using Kite API data, then generates an LLM explanation of the findings.

Agent name: Quantitative Analyst
Agent role: Evaluates price momentum, trend strength and relative performance vs Nifty 50
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from broker import get_broker
from agents.config import get_llm
from agents.analysis_state import AnalysisState
from agents.shared.data_infra import fetch_historical, fetch_nifty, resolve_instrument_tokens
from agents.shared.quant_agent import compute_indicators, compute_relative_strength


def stats_agent_node(state: AnalysisState) -> dict:
    """Compute recency + trend scores, then generate LLM explanation using Claude."""
    symbol = state["symbol"]
    try:
        broker = get_broker(state["access_token"])
        kite = broker.raw_kite

        # Resolve instrument token for this symbol
        instrument_token = state.get("instrument_token")
        if not instrument_token:
            token_map = resolve_instrument_tokens(kite)
            instrument_token = token_map.get(symbol)

        if not instrument_token:
            return {
                "stats_result": {
                    "score": 3.0,
                    "explanation": f"Instrument token not found for {symbol}.",
                }
            }

        stock_df = fetch_historical(kite, instrument_token, symbol, days=400)
        nifty_df = fetch_nifty(kite, days=400)

        if stock_df is None or stock_df.empty:
            return {
                "stats_result": {
                    "score": 3.0,
                    "explanation": f"Insufficient historical data available for {symbol} to perform technical analysis.",
                }
            }

        indicators = compute_indicators(stock_df)
        rs = compute_relative_strength(stock_df, nifty_df)

        # Compute recency score (relative strength vs Nifty, 0-5)
        stock_3m = rs.get("stock_3m_return") or 0.0
        nifty_3m = rs.get("nifty_3m_return") or 0.0
        rs_gap = stock_3m - nifty_3m
        if rs_gap >= 10:
            recency_score = 5
            recency_detail = f"Strong outperformer: +{rs_gap:.1f}% vs Nifty over 3M"
        elif rs_gap >= 5:
            recency_score = 4
            recency_detail = f"Outperformer: +{rs_gap:.1f}% vs Nifty over 3M"
        elif rs_gap >= 0:
            recency_score = 3
            recency_detail = f"In-line with Nifty: {rs_gap:+.1f}% over 3M"
        elif rs_gap >= -5:
            recency_score = 2
            recency_detail = f"Slight laggard: {rs_gap:.1f}% vs Nifty over 3M"
        else:
            recency_score = 1
            recency_detail = f"Significant underperformer: {rs_gap:.1f}% vs Nifty over 3M"

        # Compute trend score (ADX + EMA alignment, 0-5)
        adx = indicators.get("adx") or 0
        price = indicators.get("current_price") or 0
        ema_20 = indicators.get("ema_20") or 0
        ema_200 = indicators.get("ema_200") or 0

        if adx >= 30 and price > ema_20 and price > ema_200:
            trend_score = 5
            trend_strength = "Strong"
            trend_direction = "Bullish — price above EMA-20 and EMA-200 with strong ADX"
        elif adx >= 20 and price > ema_200:
            trend_score = 4
            trend_strength = "Moderate"
            trend_direction = "Bullish — price above EMA-200, ADX confirming trend"
        elif adx >= 20:
            trend_score = 3
            trend_strength = "Moderate"
            trend_direction = "Mixed — trending but price alignment weak"
        elif price > ema_200:
            trend_score = 2
            trend_strength = "Weak"
            trend_direction = "Neutral — above long-term trend but ADX weak"
        else:
            trend_score = 1
            trend_strength = "Weak"
            trend_direction = "Bearish — price below 200-EMA, no trend confirmation"

        stats_score = round((recency_score * 0.5 + trend_score * 0.5), 1)

        raw_explanation = (
            f"Recency (Relative Strength vs Nifty): {recency_score}/5 — {recency_detail}. "
            f"Trend (ADX + EMA): {trend_score}/5 — Strength: {trend_strength}, "
            f"Direction: {trend_direction}."
        )

        # Generate explanation via Claude
        try:
            llm = get_llm(temperature=0.2, provider="claude", user_id=state.get("user_id"))
            prompt = (
                f"You are a technical analysis expert specializing in Indian equity markets.\n\n"
                f"Given these technical results for {symbol}:\n\n"
                f"- Recency (Relative Strength vs Nifty 50, last 90 days): {recency_score}/5 — {recency_detail}\n"
                f"- Trend (ADX + EMA crossover): {trend_score}/5 — Strength: {trend_strength}, Direction: {trend_direction}\n"
                f"- Combined stats score: {stats_score}/5\n\n"
                "Write 2-3 sentences covering: (1) what the momentum and trend data tell you, "
                "(2) the entry implication — is now a good time to enter or wait, "
                "(3) the primary technical risk if the setup fails. Be specific with numbers."
            )
            response = llm.invoke(prompt)
            explanation = response.content.strip()
        except Exception as llm_err:
            print(f"Stats Agent LLM error for {symbol}: {llm_err}")
            explanation = raw_explanation

        return {"stats_result": {"score": stats_score, "explanation": explanation}}

    except Exception as e:
        error_msg = str(e)
        print(f"Stats Agent error for {symbol}: {error_msg}")
        explanation = f"Technical analysis could not be completed for {symbol}: {error_msg}"
        return {"stats_result": {"score": 3.0, "explanation": explanation}}
