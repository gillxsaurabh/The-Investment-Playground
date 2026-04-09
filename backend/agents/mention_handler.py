"""@Mention handler for Tipsy chatbot.

Intercepts @AgentName messages before they reach the LangGraph supervisor.
Calls the analysis agent node directly, formats the result as markdown text.

Supported @mentions:
  @QuantAnalyst SYMBOL        — Technical analysis (requires linked broker)
  @FundamentalsAnalyst SYMBOL — Fundamental analysis from Screener.in
  @NewsSentinel SYMBOL        — News sentiment via Claude
  @StockAnalysis SYMBOL       — Full 4-agent synthesis (requires linked broker)
"""

import re

from agents.analysis_state import AnalysisState
from agents.workers.stats_agent import stats_agent_node
from agents.workers.company_health_agent import company_health_agent_node
from agents.workers.breaking_news_agent import breaking_news_agent_node


# ── State builder ──────────────────────────────────────────────────────────────

def _build_state(symbol: str, access_token: str, user_id: int | None) -> AnalysisState:
    return {
        "symbol": symbol,
        "access_token": access_token,
        "instrument_token": None,
        "llm_provider": "claude",
        "user_id": user_id,
        "stats_result": None,
        "company_health_result": None,
        "breaking_news_result": None,
        "overall_score": None,
        "verdict": None,
        "risk_factors": None,
        "conflict_summary": None,
        "analyzed_at": None,
    }


# ── Helpers ────────────────────────────────────────────────────────────────────

def _strip_md(text: str) -> str:
    """Strip common markdown syntax from a string."""
    text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)   # **bold**
    text = re.sub(r"\*(.+?)\*", r"\1", text)         # *italic*
    text = re.sub(r"#{1,3}\s+", "", text)             # ### headers
    text = re.sub(r"`(.+?)`", r"\1", text)            # `code`
    return text.strip()


def _first_sentences(text: str, n: int = 2) -> str:
    """Return first n sentences stripped of markdown."""
    text = _strip_md(text)
    text = re.sub(r"\n+", " ", text).strip()
    parts = re.split(r"(?<=[.!?])\s+", text)
    return " ".join(parts[:n]).strip()


def _score_bar(score) -> str:
    """Return a compact filled/empty bar for a 0–5 score."""
    try:
        s = float(score)
        filled = round(s)
        return "█" * filled + "░" * (5 - filled) + f"  {score}/5"
    except (TypeError, ValueError):
        return f"{score}/5"


# ── Per-agent formatters ───────────────────────────────────────────────────────

def _run_quant(state: AnalysisState) -> str:
    result = stats_agent_node(state)
    r = result.get("stats_result", {})
    score = r.get("score", "N/A")
    summary = _first_sentences(r.get("explanation", "No data."), 2)
    return "\n".join([
        f"Quant Analyst — {state['symbol']}",
        f"Score  {_score_bar(score)}",
        "",
        summary,
    ])


def _run_fundamentals(state: AnalysisState) -> str:
    result = company_health_agent_node(state)
    r = result.get("company_health_result", {})
    score = r.get("score", "N/A")
    summary = _first_sentences(r.get("explanation", "No data."), 2)
    return "\n".join([
        f"Fundamentals Analyst — {state['symbol']}",
        f"Score  {_score_bar(score)}",
        "",
        summary,
    ])


def _run_news(state: AnalysisState) -> str:
    result = breaking_news_agent_node(state)
    r = result.get("breaking_news_result", {})
    score = r.get("score", "N/A")
    sentiment = (r.get("sentiment_direction") or "N/A").replace("_", " ").title()
    horizon = (r.get("time_horizon_risk") or "none").replace("_", " ").title()
    key_events = r.get("key_events", [])[:3]
    risk_flags = r.get("risk_flags", [])[:3]
    summary = _first_sentences(r.get("explanation", ""), 1)

    lines = [
        f"News Sentinel — {state['symbol']}",
        f"Score      {_score_bar(score)}",
        f"Sentiment  {sentiment}",
        f"Risk       {horizon}",
    ]
    if summary:
        lines += ["", summary]
    if key_events:
        lines += ["", "Key Events:"]
        lines += [f"• {e}" for e in key_events]
    if risk_flags:
        lines += ["", "Risk Flags:"]
        lines += [f"• {f}" for f in risk_flags]
    return "\n".join(lines)


def _run_full(state: AnalysisState) -> str:
    from agents.analysis_graph import _synthesizer_node

    # Run all 3 agents sequentially, accumulating results into state
    state.update(stats_agent_node(state))
    state.update(company_health_agent_node(state))
    state.update(breaking_news_agent_node(state))
    state.update(_synthesizer_node(state))

    symbol = state["symbol"]
    sq = (state.get("stats_result") or {}).get("score", "N/A")
    sf = (state.get("company_health_result") or {}).get("score", "N/A")
    sn = (state.get("breaking_news_result") or {}).get("score", "N/A")
    overall = state.get("overall_score", "N/A")
    verdict = _first_sentences(state.get("verdict") or "No verdict.", 2)
    risk_factors = (state.get("risk_factors") or [])[:2]
    conflict = state.get("conflict_summary")

    lines = [
        f"Stock Analysis — {symbol}",
        f"Overall  {_score_bar(overall)}",
        "",
        "Agent                Score",
        "───────────────────  ─────",
        f"Quant Analyst        {sq}/5",
        f"Fundamentals         {sf}/5",
        f"News Sentinel        {sn}/5",
        "",
        f"Verdict: {verdict}",
    ]
    if risk_factors:
        lines += ["", "Key Risks:"]
        lines += [f"• {rf}" for rf in risk_factors]
    if conflict:
        lines += ["", f"Signal Note: {_first_sentences(conflict, 1)}"]
    return "\n".join(lines)


# ── Mention registry ───────────────────────────────────────────────────────────
# (mention_key_lowercase, display_name, needs_broker, handler)

_MENTION_MAP: dict[str, tuple[str, bool, object]] = {
    "quantanalyst":        ("Quant Analyst",        True,  _run_quant),
    "fundamentalsanalyst": ("Fundamentals Analyst", False, _run_fundamentals),
    "newssentinel":        ("News Sentinel",        False, _run_news),
    "stockanalysis":       ("Full Stock Analysis",  True,  _run_full),
}

_MENTION_RE = re.compile(r"@([A-Za-z]+)", re.IGNORECASE)
_SYMBOL_RE = re.compile(r"\b([A-Z][A-Z0-9&]{1,19})\b")

# Common all-caps words that are not NSE tickers
_SKIP_TOKENS = {
    "I", "A", "AI", "AN", "OR", "IN", "TO", "CAN", "YOU",
    "NSE", "BSE", "THE", "AND", "FOR", "ME", "MY", "ON",
}


def _extract_symbol(text: str) -> str | None:
    """Find the first NSE-style ticker (2-20 uppercase alphanum chars) in text."""
    for m in _SYMBOL_RE.finditer(text):
        token = m.group(1)
        if token in _SKIP_TOKENS:
            continue
        if len(token) >= 2:
            return token
    return None


# ── Public entry point ─────────────────────────────────────────────────────────

def handle_mention(message: str, access_token: str, user_id: int | None) -> str | None:
    """Return a formatted agent response if message contains a recognized @mention.

    Returns None if no @mention found — caller falls through to LangGraph.
    Called by run_agent() before the supervisor graph is invoked.
    """
    match = _MENTION_RE.search(message)
    if not match:
        return None

    mention_key = match.group(1).lower()
    if mention_key not in _MENTION_MAP:
        return None

    display_name, needs_broker, handler_fn = _MENTION_MAP[mention_key]

    # Strip @mention from the message before extracting the symbol.
    # Keep original casing — NSE tickers are uppercase; lowercase words are not symbols.
    stripped = _MENTION_RE.sub("", message).strip()
    symbol = _extract_symbol(stripped)

    if not symbol:
        return (
            f"Please specify an NSE stock symbol. "
            f"Example: @{match.group(1)} TATAMOTORS"
        )

    if needs_broker and not access_token:
        return (
            f"{display_name} requires a linked Zerodha broker account. "
            "Link it in Account \u2192 Broker settings, then try again."
        )

    state = _build_state(symbol, access_token, user_id)

    try:
        return handler_fn(state)
    except Exception as e:
        print(f"[MentionHandler] {display_name} failed for {symbol}: {e}")
        return f"{display_name} analysis failed for {symbol}: {str(e)}"
