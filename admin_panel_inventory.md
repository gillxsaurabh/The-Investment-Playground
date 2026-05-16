# Admin Panel — Configurable Analysis Parameters Inventory

> Complete catalog of every parameter that influences stock-analysis output across the **Discovery (buy)** pipeline, **Audit (sell)** pipeline, and **Dashboard health** view. Each entry shows current value, source file + line, what it controls, and which pipeline consumes it.
>
> **Total: 117 numerical parameters + 9 LLM prompts = 126 items.**
>
> *Excluded from this inventory* (not stock-analysis): simulator spread/capital, API rate limits, cache TTLs, live-trading position caps, automation drawdown halts, trail-multipliers, stall-exit days.

---

## Summary

| # | Category | Count | Pipelines |
|---|---|---|---|
| 1 | Technical indicator periods | 6 | Buy + Sell |
| 2 | Buy gear profiles (5 gears × 5 params) | 25 | Buy |
| 3 | Buy pipeline filter thresholds | 7 | Buy |
| 4 | Composite scoring weights | 4 | Buy |
| 5 | Final ranking weights (Agent 6) | 5 | Buy |
| 6 | Market regime — VIX tiers | 5 | Buy |
| 7 | News sentiment | 2 | Buy + Sell + Dashboard |
| 8 | Fundamental quality tiers | 6 | All |
| 9 | Relative strength thresholds | 4 | All |
| 10 | Sell pipeline trigger thresholds | 14 | Sell |
| 11 | Sell urgency scoring points (per signal) | 22 | Sell |
| 12 | Sell urgency score bands | 4 | Sell |
| 13 | Dashboard health score weights | 5 | Dashboard |
| 14 | Dashboard health score bands | 4 | Dashboard |
| 15 | LLM model + thinking budgets | 4 | All |
| | **Numerical subtotal** | **117** | |
| 16 | LLM analysis prompts | 9 | All |
| | **Grand total** | **126** | |

---

## 1. Technical Indicator Periods (6)

Used by both buy and sell pipelines. Changing these forces recomputation of all indicators.

| Param | Current | File | Line | What it controls |
|---|---|---|---|---|
| `ADX_PERIOD` | 14 | `backend/constants.py` | 9 | Bars for ADX smoothing (Wilder) |
| `EMA_SHORT` | 20 | `backend/constants.py` | 10 | Short-term MA (entry signal) |
| `EMA_LONG` | 50 | `backend/constants.py` | 11 | Intermediate-term MA |
| `EMA_TREND` | 200 | `backend/constants.py` | 12 | Long-term MA (trend filter) |
| `RSI_PERIOD` | 14 | `backend/constants.py` | 13 | RSI calculation period |
| `ATR_PERIOD` | 14 | `backend/constants.py` | 14 | ATR period for volatility |

---

## 2. Buy Gear Profiles (25 — 5 gears × 5 params each)

Each "gear" is a complete strategy preset selected by the user before a discovery run. Located in `backend/agents/decision_support/strategy_config.py`.

### Gear 1 — Fortress (ultra-conservative)
| Param | Current | Line | What it controls |
|---|---|---|---|
| `universe` | `nifty100` | 23 | Stock universe |
| `min_turnover` | 500,000,000 | 24 | Liquidity floor (20-day avg, ₹) |
| `rsi_buy_limit` | 30 | 25 | Entry RSI threshold |
| `fundamental_check` | `strict` | 26 | ROE ≥15% & D/E ≤1.0 enforced |
| `atr_stop_loss_multiplier` | 2.0 | 27 | Stop = entry − 2 × ATR |

### Gear 2 — Cautious
| Param | Current | Line | What it controls |
|---|---|---|---|
| `universe` | `nifty100` | 31 | Stock universe |
| `min_turnover` | 100,000,000 | 32 | Liquidity floor (₹) |
| `rsi_buy_limit` | 35 | 33 | Entry RSI threshold |
| `fundamental_check` | `standard` | 34 | Profit growth check |
| `atr_stop_loss_multiplier` | 1.75 | 35 | Stop multiplier |

### Gear 3 — Balanced (default)
| Param | Current | Line | What it controls |
|---|---|---|---|
| `universe` | `nifty500` | 39 | Stock universe |
| `min_turnover` | 50,000,000 | 40 | Liquidity floor (₹) |
| `rsi_buy_limit` | 40 | 41 | Entry RSI threshold |
| `fundamental_check` | `standard` | 42 | Profit growth check |
| `atr_stop_loss_multiplier` | 1.5 | 43 | Stop multiplier |

### Gear 4 — Growth
| Param | Current | Line | What it controls |
|---|---|---|---|
| `universe` | `nifty_midcap150` | 47 | Mid-cap focus |
| `min_turnover` | 20,000,000 | 48 | Liquidity floor (₹) |
| `rsi_buy_limit` | 50 | 49 | Entry RSI threshold |
| `fundamental_check` | `loose` | 50 | Minimal checks |
| `atr_stop_loss_multiplier` | 1.25 | 51 | Stop multiplier |

### Gear 5 — Turbo
| Param | Current | Line | What it controls |
|---|---|---|---|
| `universe` | `nifty_smallcap250` | 55 | Small-cap |
| `min_turnover` | 5,000,000 | 56 | Liquidity floor (₹) |
| `rsi_buy_limit` | 60 | 57 | Entry RSI threshold |
| `fundamental_check` | `none` | 58 | Skip fundamentals |
| `atr_stop_loss_multiplier` | 1.0 | 59 | Stop multiplier |

---

## 3. Buy Pipeline Filter Thresholds (7)

Cross-cutting filters applied during the 5-agent funnel.

| Param | Current | File | Line | What it controls |
|---|---|---|---|---|
| `ADX_PIPELINE_MIN` | 20 | `backend/constants.py` | 21 | Min ADX for trend confirmation (Quant filter) |
| `STRICT_ROE_MIN` | 15 | `backend/constants.py` | 22 | Min ROE % under Gear 1 strict mode |
| `STRICT_DE_MAX` | 1.0 | `backend/constants.py` | 23 | Max D/E under Gear 1 strict mode |
| `MIN_VOLUME_RATIO` | 0.7 | `backend/constants.py` | 28 | 5d/20d volume ratio floor (distribution check) |
| `SECTOR_5D_TOLERANCE` | -0.5 | `backend/constants.py` | 24 | Allow sector 5-day change down to this % |
| `SECTOR_HISTORY_CALENDAR_DAYS` | 15 | `backend/constants.py` | 25 | Sector data lookback window |
| `YOY_QUARTERS_NEEDED` | 5 | `backend/constants.py` | 29 | Min quarters for YoY profit comparison |

---

## 4. Composite Scoring Weights (4)

Used by the Quant Analyst (Agent 2) to compute the 0–100 composite score. Must sum to 1.0.

| Param | Current | File | Line | What it controls |
|---|---|---|---|---|
| `WEIGHT_RECENCY` | 0.25 | `backend/constants.py` | 45 | 3M relative strength vs Nifty |
| `WEIGHT_TREND` | 0.25 | `backend/constants.py` | 46 | ADX + EMA alignment |
| `WEIGHT_FUNDAMENTALS` | 0.30 | `backend/constants.py` | 47 | Profit growth & ROE |
| `WEIGHT_AI_SENTIMENT` | 0.20 | `backend/constants.py` | 48 | News sentiment from Claude |

---

## 5. Final Ranking Weights — Agent 6 (5)

Combines AI conviction with quantitative factors to produce final rank. Must sum to 1.0.

| Param | Current | File | Line | What it controls |
|---|---|---|---|---|
| AI conviction weight | 0.35 | `backend/agents/decision_support/tools.py` | 761 | AI model's 1–10 conviction score |
| Composite score weight | 0.25 | `backend/agents/decision_support/tools.py` | 762 | Stage-5 composite 0–100 |
| Relative strength weight | 0.15 | `backend/agents/decision_support/tools.py` | 763 | 3M stock return vs Nifty |
| Fundamental weight | 0.15 | `backend/agents/decision_support/tools.py` | 764 | ROE + D/E + profit growth |
| Sector momentum weight | 0.10 | `backend/agents/decision_support/tools.py` | 765 | Sector 5d performance |

---

## 6. Market Regime — VIX Tiers (5)

Dynamically tightens buy criteria when India VIX is elevated.

| Param | Current | File | Line | What it controls |
|---|---|---|---|---|
| `VIX_TIER1_THRESHOLD` | 20 | `backend/constants.py` | 36 | Enter Tier 1 (mild caution) |
| `VIX_TIER2_THRESHOLD` | 25 | `backend/constants.py` | 37 | Enter Tier 2 (high fear → restrict aggressive gears) |
| `VIX_TIER3_THRESHOLD` | 30 | `backend/constants.py` | 38 | Tier 3 — pause automation entirely |
| `VIX_TIER1_RSI_TIGHTEN` | 3 | `backend/constants.py` | 39 | Raise RSI buy limit by this when in Tier 1 |
| `VIX_TIER2_RSI_TIGHTEN` | 7 | `backend/constants.py` | 40 | Raise RSI buy limit by this when in Tier 2 |

---

## 7. News Sentiment (2)

| Param | Current | File | Line | What it controls |
|---|---|---|---|---|
| `NEWS_LOOKBACK_DAYS` | 7 | `backend/constants.py` | 41 | News fetch window per stock |
| `NEWS_NEGATIVE_THRESHOLD` | 2 | `backend/constants.py` | 42 | AI sentiment score < this triggers warning flag |

---

## 8. Fundamental Quality Tiers (6)

ROE and D/E bands used across buy filters, sell signals, and dashboard health.

| Param | Current | File | Line | What it controls |
|---|---|---|---|---|
| `ROE_EXCELLENT` | 15 | `backend/constants.py` | 51 | Excellent capital efficiency (%) |
| `ROE_GOOD` | 10 | `backend/constants.py` | 52 | Good returns (%) |
| `ROE_POOR` | 5 | `backend/constants.py` | 53 | Below-average (%) |
| `DE_LOW` | 1.0 | `backend/constants.py` | 54 | Conservative leverage |
| `DE_MODERATE` | 2.0 | `backend/constants.py` | 55 | Moderate leverage |
| `DE_HIGH` | 3.0 | `backend/constants.py` | 56 | High leverage risk |

---

## 9. Relative Strength Thresholds (4)

| Param | Current | File | Line | What it controls |
|---|---|---|---|---|
| `RS_STRONG_OUTPERFORM` | 5 | `backend/constants.py` | 75 | Outperformance buffer vs Nifty (%) |
| `RS_UNDERPERFORM` | -5 | `backend/constants.py` | 76 | Underperformance threshold (%) |
| `ADX_STRONG_TREND` | 25 | `backend/constants.py` | 79 | ADX confirming strong trend |
| `ADX_MODERATE_TREND` | 20 | `backend/constants.py` | 80 | ADX confirming moderate trend |

---

## 10. Sell Pipeline Trigger Thresholds (14)

Numeric thresholds the Sell Signal Engine checks per holding.

| Param | Current | File | Line | What it controls |
|---|---|---|---|---|
| `SELL_RSI_OVERBOUGHT` | 70 | `backend/constants.py` | 101 | RSI above this = profit-taking signal |
| `SELL_RSI_MOMENTUM_FAILED` | 40 | `backend/constants.py` | 102 | RSI below this after being >50 = reversal |
| `SELL_ADX_WEAK` | 20 | `backend/constants.py` | 103 | ADX below this + falling = trend breakdown |
| `SELL_RS_NIFTY_GAP` | -10 | `backend/constants.py` | 104 | 3M return vs Nifty < this = laggard (%) |
| `SELL_RS_SECTOR_GAP` | -10 | `backend/constants.py` | 105 | 3M return vs sector < this = sector laggard (%) |
| `SELL_PROFIT_DECLINE_QUARTERS` | 2 | `backend/constants.py` | 106 | Consecutive declining quarters → flag |
| `SELL_ROE_WEAK` | 10 | `backend/constants.py` | 107 | ROE below this = red flag (%) |
| `SELL_ROE_MODERATE` | 15 | `backend/constants.py` | 108 | ROE below this = minor flag (%) |
| `SELL_DE_HIGH` | 3.0 | `backend/constants.py` | 109 | D/E above this = high debt flag |
| `SELL_PNL_LOSS_THRESHOLD` | -15 | `backend/constants.py` | 110 | Unrealized P&L below this triggers SL review (%) |
| `SELL_PNL_DEEP_LOSS_THRESHOLD` | -25 | `backend/constants.py` | 111 | Deep loss threshold (%) |
| `SELL_HISTORICAL_DAYS` | 400 | `backend/constants.py` | 156 | OHLCV lookback for sell analysis |
| `SELL_MOMENTUM_LOOKBACK` | 10 | `backend/constants.py` | 157 | Days window for RSI momentum failure detection |
| `SELL_VOLUME_DRY_RATIO` | 0.60 | `backend/constants.py` | 158 | 5d/20d volume below this = volume dry-up |

---

## 11. Sell Urgency Scoring Points (22 — per signal)

Point values awarded per signal that fires. Sum maps to total urgency (0–100). Defined as literals in `backend/agents/decision_support/sell_tools.py`.

### Technical breakdown (max 56)
| Signal | Points | Line | Trigger |
|---|---|---|---|
| Price < EMA-200 | 15 | 214 | Long-term trend broken |
| RSI > overbought | 10 | 219 | Profit-taking signal |
| RSI momentum failed | 8 | 226 | RSI below 40 after being >50 |
| ADX weak | 7 | 235 | ADX < threshold + falling |
| Price < EMA-50 | 5 | 239 | Intermediate trend lost |
| Price < EMA-20 | 3 | 244 | Short-term trend weak |
| Volume drying near highs | 8 | 250 | 5d/20d ratio < dry threshold |

### Relative weakness (max 25)
| Signal | Points | Line | Trigger |
|---|---|---|---|
| Underperforms Nifty >10% (3M) | 12 | 278 | Lagging benchmark |
| Underperforms Nifty 5–10% | 7 | 284 | Moderate underperformance |
| Underperforms Nifty 2–5% | 4 | 290 | Minor underperformance |
| Underperforms sector >10% | 13 | 297 | Sector laggard |
| Underperforms sector 5–10% | 8 | 302 | Sector relative weakness |

### Fundamental flags (max 41)
| Signal | Points | Line | Trigger |
|---|---|---|---|
| Profit declining 2+ quarters | 15 | 323 | Earnings deterioration |
| QoQ profit decline | 7 | 328 | Monitor for reversal |
| YoY profit declining | 10 | 333 | Fundamental weakness |
| ROE below weak threshold | 8 | 339 | Poor capital efficiency |
| ROE below moderate threshold | 4 | 342 | Marginal ROE |
| D/E above high threshold | 7 | 348 | High leverage risk |

### Position health (max 46)
| Signal | Points | Line | Trigger |
|---|---|---|---|
| P&L < deep loss threshold | 20 | 361 | Deep stop-loss review |
| P&L < loss threshold | 14 | 366 | Significant loss |
| P&L between -5% and -15% | 8 | 369 | Moderate loss |
| P&L between -2% and -5% | 4 | 372 | Minor loss |

---

## 12. Sell Urgency Score Bands (4)

Map total urgency score (0–100) to verdict.

| Verdict | Score | File | Line | Meaning |
|---|---|---|---|---|
| `STRONG SELL` | ≥ 70 | `backend/constants.py` | 128 | Immediate exit recommended |
| `SELL` | 40–69 | `backend/constants.py` | 129 | Consider exiting |
| `WATCH` | 20–39 | `backend/constants.py` | 130 | Monitor closely |
| `HOLD` | < 20 | `backend/constants.py` | 131 | No exit signal |

---

## 13. Dashboard Health Score Weights (5)

Weights for the on-demand stock health analyzer (audit dashboard). Sum to 10.0.

| Component | Weight | File | Line | Inputs |
|---|---|---|---|---|
| Technical | 3.0 | `backend/constants.py` | 134 | RSI, ADX, EMA alignment, volume |
| Fundamental | 2.5 | `backend/constants.py` | 135 | ROE, D/E, profit trend |
| Relative strength | 2.0 | `backend/constants.py` | 136 | 3M vs Nifty + sector |
| News sentiment | 1.5 | `backend/constants.py` | 137 | Claude news analysis |
| Position health | 1.0 | `backend/constants.py` | 138 | Unrealized P&L % |

---

## 14. Dashboard Health Score Bands (4)

| Verdict | Score | File | Line | Action |
|---|---|---|---|---|
| `HEALTHY` | 7–10 | `backend/constants.py` | 141 | Hold / accumulate |
| `STABLE` | 5–7 | `backend/constants.py` | 142 | Monitor |
| `WATCH` | 3–5 | `backend/constants.py` | 143 | Review position |
| `CRITICAL` | < 3 | `backend/constants.py` | 144 | Consider exit |

---

## 15. LLM Model + Thinking Budgets (4)

Affects analysis quality and cost.

| Param | Current | File | Line | What it controls |
|---|---|---|---|---|
| `CLAUDE_MODEL_DEFAULT` | `claude-sonnet-4-6` | `backend/constants.py` | 96 | Default Claude model |
| `CLAUDE_SYNTHESIS_THINKING_BUDGET` | 5000 | `backend/constants.py` | 97 | Tokens for analysis synthesizer |
| `CLAUDE_CONVICTION_THINKING_BUDGET` | 10000 | `backend/constants.py` | 98 | Tokens for buy + sell conviction engines |
| `AUDIT_AI_THINKING_BUDGET` | 10000 | `backend/constants.py` | 147 | Tokens for audit dashboard AI |

---

## 16. LLM Analysis Prompts (9)

System prompts that shape every AI-driven analysis output. All are currently inline in Python source (f-strings with variable interpolation). For admin editing, each will need to be extracted into a named template with `{var}` placeholders.

| # | Prompt name | Pipeline | File | Lines | Provider | Extended thinking | Output format |
|---|---|---|---|---|---|---|---|
| 1 | **AI Conviction Engine** | Buy — Agent 5 | `backend/agents/decision_support/tools.py` | 587–607 | Claude Sonnet 4.6 | Yes (10k) | JSON: conviction (1–10), reason, primary_risk, trade_type, news_sentiment, news_flag |
| 2 | **Portfolio Ranker** | Buy — Agent 6 | `backend/agents/decision_support/tools.py` | 798–813 | OpenAI gpt-4o-mini | No | JSON: rank_reason, portfolio_note |
| 3 | **Sell Signal Engine** | Sell — Stage 5 | `backend/agents/decision_support/sell_tools.py` | 489–507 | Claude Sonnet 4.6 | Yes (10k) | JSON: sell_conviction (1–10), sell_reason, hold_reason, news_sentiment, news_flag |
| 4 | **Quantitative Analyst** | Dashboard scatter-gather | `backend/agents/workers/stats_agent.py` | 115–124 | Claude Sonnet 4.6 | No | 2–3 sentences (RS, trend, technical risk) |
| 5 | **Fundamentals Analyst** | Dashboard scatter-gather | `backend/agents/workers/company_health_agent.py` | 46–55 | Claude Sonnet 4.6 | No | 2–3 sentences (balance sheet, earnings, risk) |
| 6 | **News Sentinel** | Dashboard scatter-gather | `backend/agents/workers/breaking_news_agent.py` | 25–49 | Claude Sonnet 4.6 | No | JSON: score, explanation, key_events, risk_flags, sentiment_direction, time_horizon_risk |
| 7 | **Synthesizer** | Dashboard scatter-gather | `backend/agents/analysis_graph.py` | 68–83 | Claude Sonnet 4.6 | Yes (5k) | JSON: overall_score, verdict, risk_factors, conflict_summary, confidence |
| 8 | **General Chat Agent** | Chat | `backend/agents/workers/general_agent.py` | 3–9 | OpenAI | No | Chat text |
| 9 | **Portfolio Chat Agent** | Chat | `backend/agents/workers/portfolio_agent.py` | 13–21 | OpenAI | No | Chat text (tool-augmented) |

---

## Scope Recommendations for v1 Admin Panel

Three possible cuts based on the inventory above:

- **Core (~50 items)** — Sections 2, 4, 5, 10, 12, 16. Drives buy/sell decisions most directly.
- **Broad (~85 items)** — Above + sections 6, 8, 9, 13, 14, 15. Adds dashboard + market-regime + LLM tuning. **Recommended.**
- **Full (126 items)** — Everything in this document including indicator periods and granular urgency points.

---

## Open Questions Before Implementation

1. **Scope cut** — core, broad, or full?
2. **Live-reload mechanism** — in-process cache invalidation on save, restart, or manual "reload config" button?
3. **Prompt-editing format** — full template with `{var}` placeholders, or split into editable instructions + code-generated data block?
4. **Audit log** — full history (who/when/old/new), last-modified metadata only, or none?
5. **Per-user override vs global only** — should premium users get to tweak some params for themselves, or are all changes platform-wide?
