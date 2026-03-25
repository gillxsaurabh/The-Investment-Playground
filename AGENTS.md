# CogniCap — Agent Catalogue

CogniCap uses two distinct agent systems built on LangGraph + Gemini LLM:

1. **Stock Discovery Pipeline** — a sequential 5-agent pipeline that filters the Nifty universe down to a final shortlist of high-conviction trade candidates (`/api/decision-support/run`)
2. **Chat & Deep Analysis System** — a supervisor-routed multi-agent graph that handles live chat (`/api/chat/send`) and on-demand single-stock deep dives (`/api/analyze-*`)

---

## System 1 — Stock Discovery Pipeline (`agents/decision_support/`)

Triggered by "Discover Stocks" in the Trading Agent screen. Agents run **sequentially**; each one receives the filtered output of the previous step. Progress is streamed live to the UI via SSE.

```
Nifty 500 (500 stocks)
    │
    ▼  Agent 1: Market Scanner
    │  ~50–100 stocks
    ▼  Agent 2: Quant Analyst
    │  ~10–30 stocks
    ▼  Agent 3: Fundamentals Analyst
    │  ~5–15 stocks
    ▼  Agent 4: Sector Momentum
    │  ~2–10 stocks
    ▼  Agent 5: AI Conviction Engine
    │
    └─ Final ranked shortlist (3–5 stocks)
```

---

### Agent 1 — Market Scanner

| Property | Detail |
|---|---|
| **File** | `agents/decision_support/tools.py` → `filter_market_universe()` |
| **Step ID** | `universe_filter` |
| **Input** | Full universe CSV (Nifty 100 / 500 / Midcap 150 / Smallcap 250, selected by gear) |
| **Output** | Stocks passing all 5 filters |
| **LLM** | No — pure rule-based logic |

**What it does:**

Scans the entire stock universe and keeps only stocks that show genuine institutional interest and an established uptrend. Applies 5 sequential filters:

1. **Turnover filter** — 20-day avg daily turnover must exceed the gear minimum (₹5 Cr – ₹500 Cr). Removes illiquid stocks.
2. **Volume trend filter** — 5-day avg volume ÷ 20-day avg volume ≥ 0.7. Catches stocks where sellers are quietly distributing.
3. **200-EMA filter** — Current price must be above the 200-day EMA. Confirms macro uptrend.
4. **Nifty relative strength** — 3-month stock return must beat the Nifty 50 return. Only outperforming stocks.
5. **Sector relative strength** — 3-month stock return must beat its sector index return. Best stock in its own sector.

**Gear impact:** Universe size and minimum turnover threshold change per gear (Fortress = Nifty 100, Turbo = Smallcap 250).

---

### Agent 2 — Quant Analyst

| Property | Detail |
|---|---|
| **File** | `agents/decision_support/tools.py` → `analyze_technicals()` |
| **Step ID** | `technical_setup` |
| **Input** | Stocks from Market Scanner |
| **Output** | Stocks with a valid RSI entry trigger |
| **LLM** | No — pure quantitative logic |

**What it does:**

Runs quantitative technical analysis to find stocks with high-probability entry setups. A stock must have both:

1. **ADX ≥ 20** — Trend strength gate. ADX below 20 means the trend is too weak to trade.
2. **A valid RSI trigger** — One of two entry patterns:
   - **Pullback trigger:** RSI < `rsi_buy_limit` (25–55 by gear) AND price > 200-EMA. Catching a healthy dip within a confirmed uptrend.
   - **Momentum trigger:** RSI crossed above 50 in the last 5 sessions AND price > 20-EMA. Catching a fresh breakout with momentum.

Adds `rsi`, `adx`, `ema_20`, `ema_200`, and `rsi_trigger` fields to each stock for downstream agents and the UI.

**Gear impact:** `rsi_buy_limit` rises from 30 (Fortress — deep dip only) to 60 (Turbo — any RSI level).

---

### Agent 3 — Fundamentals Analyst

| Property | Detail |
|---|---|
| **File** | `agents/decision_support/tools.py` → `check_fundamentals()` |
| **Step ID** | `fundamentals` |
| **Input** | Stocks from Quant Analyst |
| **Output** | Stocks with acceptable financial health |
| **LLM** | No — web scraping + rule logic |
| **Data source** | Screener.in (scraped in real time) |

**What it does:**

Scrapes [Screener.in](https://www.screener.in) for each stock's quarterly financial data and applies fundamental quality filters. Filter mode depends on the selected gear:

| Mode | Gear | Criteria |
|---|---|---|
| `strict` | Fortress | YoY quarterly profit growth **AND** ROE > 15% **AND** D/E < 1.0 |
| `standard` | Cautious / Balanced | YoY quarterly profit growth (falls back to QoQ if only 4 quarters available) |
| `loose` | Growth | Latest quarter net profit > 0 |
| `none` | Turbo | Skipped entirely |

Adds `roe`, `debt_to_equity`, and `profit_yoy_growing` fields to each stock.

---

### Agent 4 — Sector Momentum

| Property | Detail |
|---|---|
| **File** | `agents/decision_support/tools.py` → `check_sector_health()` |
| **Step ID** | `sector_health` |
| **Input** | Stocks from Fundamentals Analyst |
| **Output** | Stocks whose sector index has positive recent momentum |
| **LLM** | No — Kite API historical data |

**What it does:**

Checks whether each stock's sector has positive 5-trading-day momentum. A sector in a downtrend creates a headwind even for strong individual stocks.

Logic:
- Fetches 15 calendar days of daily OHLC for the sector index from Kite API
- Calculates: `sector_5d_change = (close[-1] – close[-5]) / close[-5] × 100`
- Keeps the stock if `sector_5d_change ≥ –0.5%` (allows minor weakness, rejects declining sectors)

Adds `sector_5d_change` to each stock. Uses a sector-to-index mapping from `data/sector_indices.json`.

---

### Agent 5 — AI Conviction Engine

| Property | Detail |
|---|---|
| **File** | `agents/decision_support/tools.py` → `compute_composite_scores()` + `ai_rank_stocks()` |
| **Step ID** | `ai_ranking` |
| **Input** | Stocks from Sector Momentum |
| **Output** | Stocks scored 0–100 and ranked by AI conviction (1–10) |
| **LLM** | Yes — Gemini (with OpenAI fallback) |

**What it does (two sub-steps):**

**Step A — Composite Scoring (rule-based, fast):**

Assigns each stock a 0–100 score across 4 dimensions (25 pts each):

| Dimension | How scored |
|---|---|
| Technical (0–25) | RSI quality (pullback = 0–10, momentum = 5) + ADX strength (min 10, ADX÷4) + EMA distance (min 5) |
| Fundamental (0–25) | Profit growth (+8/+7) + ROE tier (> 20% = +10, > 15% = +7, > 10% = +4) |
| Relative Strength (0–25) | Nifty outperformance (min 15) + Sector outperformance (min 10) |
| Volume Health (0–25) | Volume ratio (min 15) + Turnover magnitude (min 10) |

**Step B — AI Ranking (LLM-powered):**

1. Fetches recent news headlines for each stock via Google News RSS (7-day lookback, max 10 headlines per stock)
2. Sends all stock data + news to Gemini with the current market regime (VIX level) as context
3. LLM returns for each stock:
   - `ai_conviction`: 1–10 score
   - `reason`: 1-sentence explanation
   - `news_sentiment`: 1–5 score
   - `news_flag`: `"clear"` or `"warning"`
4. Final ranking: AI conviction (primary) → composite score (secondary)

---

## System 2 — Chat & Deep Analysis (`agents/`)

Used by the Chat panel and the stock health analysis cards on the Dashboard. Two separate LangGraph graphs handle these flows.

---

### Routing Supervisor

| Property | Detail |
|---|---|
| **File** | `agents/supervisor.py` → `_supervisor_node()` |
| **Role** | Intent classifier — reads the user's message and routes to the right worker |
| **LLM** | Yes — Gemini at temperature 0 |
| **Graph** | `agents/supervisor.py` → `build_graph()` |

**What it does:**

Entry point for all chat messages. Uses an LLM to classify intent and select the appropriate worker agent. Returns only the worker name — no content generation. Falls back to `general_agent` if intent is unclear.

```
User message
    │
    ▼  Supervisor (LLM classifier)
    │
    ├─── "portfolio_agent"  →  Portfolio Agent Worker
    └─── "general_agent"   →  General Agent Worker
```

---

### Portfolio Agent

| Property | Detail |
|---|---|
| **File** | `agents/workers/portfolio_agent.py` |
| **Triggered by** | Supervisor when user asks about their holdings, P&L, or specific stocks |
| **LLM** | Yes — Gemini ReAct agent |
| **Framework** | LangGraph ReAct (tool-calling loop) |

**Tools available:**

| Tool | What it fetches |
|---|---|
| `get_portfolio_holdings` | Live holdings list with quantities, avg cost, current value, P&L |
| `get_portfolio_summary` | Aggregated P&L, total invested, overall gain/loss % |
| `analyze_stock_health` | Triggers deep analysis for a specific stock symbol |
| `get_market_indices` | Nifty 50 and Sensex current levels |

Fetches real data from Kite API via the broker abstraction before answering. Always formats values in INR (₹).

---

### General Agent

| Property | Detail |
|---|---|
| **File** | `agents/workers/general_agent.py` |
| **Triggered by** | Supervisor for general trading questions, market education, non-portfolio queries |
| **LLM** | Yes — Gemini ReAct agent |
| **Tools** | None — knowledge only |

**What it does:**

Answers general trading and finance questions from LLM knowledge — concepts like RSI, ADX, how trailing stops work, sector rotation, etc. Has no access to the user's portfolio or live market data. If the user asks about their specific holdings, it redirects them to the portfolio specialist.

---

### Quantitative Analyst (Deep Analysis)

| Property | Detail |
|---|---|
| **File** | `agents/workers/stats_agent.py` → `stats_agent_node()` |
| **Triggered by** | Analysis graph (parallel, not chat) |
| **LLM** | Yes — Gemini for explanation generation |

**What it does:**

Runs technical analysis for a single stock as part of a deep-dive. Uses the `StockAnalyzer` to compute:
- **Recency score (0–5):** Relative strength vs Nifty 50 over the last 90 days
- **Trend score (0–5):** ADX strength + EMA crossover direction

Combined stats score = `(recency × 0.5) + (trend × 0.5)`. Then calls Gemini to write a 2–3 sentence plain-English explanation of the numbers. Falls back to a structured text summary if LLM fails.

---

### Fundamentals Analyst (Deep Analysis)

| Property | Detail |
|---|---|
| **File** | `agents/workers/company_health_agent.py` → `company_health_agent_node()` |
| **Triggered by** | Analysis graph (parallel, not chat) |
| **LLM** | Yes — Gemini for explanation generation |
| **Data source** | Screener.in |

**What it does:**

Scrapes Screener.in for a single stock's balance-sheet data — ROE, Debt/Equity ratio, and Sales Growth — then computes a fundamental health score (0–5). Calls Gemini to write a 2–3 sentence explanation citing specific numbers and the scoring logic (e.g., ROE > 15% with D/E < 1 is excellent). Falls back to a structured text summary if LLM fails.

---

### News Sentinel (Deep Analysis)

| Property | Detail |
|---|---|
| **File** | `agents/workers/breaking_news_agent.py` → `breaking_news_agent_node()` |
| **Triggered by** | Analysis graph (parallel, not chat) |
| **LLM** | Yes — Gemini, temperature 0.3 |

**What it does:**

Calls Gemini with a structured prompt to assess the news sentiment for a stock. The LLM is asked to evaluate (from its training data + reasoning):

1. Recent quarterly earnings and management guidance
2. Major corporate actions (M&A, fundraising, restructuring)
3. Regulatory or governance concerns (SEBI, auditor flags, promoter pledging)
4. Sector-level tailwinds or headwinds
5. Any breaking or material news from the last 30 days

Returns a `score` (1–5) and a 3–4 sentence `explanation`. Scoring guide: 5 = strong positive (earnings beat), 3 = neutral/mixed, 1 = high risk (fraud, bankruptcy concerns).

---

### Analysis Synthesizer

| Property | Detail |
|---|---|
| **File** | `agents/analysis_graph.py` → `_synthesizer_node()` |
| **Triggered by** | Analysis graph — after all 3 parallel agents complete |
| **LLM** | Yes — Gemini at temperature 0.1 |

**What it does:**

Fan-in node that collects results from all three parallel analysis agents and produces a final verdict. Passes all three scores and explanations to Gemini and asks for:

- A weighted **overall score** (1–5, one decimal)
- A one-line **action recommendation**: Strong Buy / Buy / Accumulate / Hold / Reduce / Exit with reasoning

Falls back to a plain average of the three scores and a "Hold" verdict if LLM is unavailable or rate-limited.

```
Quantitative Analyst  ─┐
Fundamentals Analyst  ─┤── Synthesizer ──► overall_score + verdict
News Sentinel         ─┘
```

---

## Agent Map Summary

| Agent | System | Type | LLM | Runs |
|---|---|---|---|---|
| Market Scanner | Discovery Pipeline | Rule-based filter | No | Sequential step 1 |
| Quant Analyst | Discovery Pipeline | Rule-based filter | No | Sequential step 2 |
| Fundamentals Analyst | Discovery Pipeline | Web scrape + rules | No | Sequential step 3 |
| Sector Momentum | Discovery Pipeline | Kite API + rules | No | Sequential step 4 |
| AI Conviction Engine | Discovery Pipeline | Composite score + LLM | Yes | Sequential step 5 |
| Routing Supervisor | Chat System | LLM intent classifier | Yes | Every chat message |
| Portfolio Agent | Chat System | ReAct tool-calling | Yes | On routing |
| General Agent | Chat System | LLM knowledge only | Yes | On routing |
| Quantitative Analyst | Deep Analysis | Technical computation + LLM explain | Yes | Parallel |
| Fundamentals Analyst | Deep Analysis | Scrape + LLM explain | Yes | Parallel |
| News Sentinel | Deep Analysis | LLM sentiment | Yes | Parallel |
| Analysis Synthesizer | Deep Analysis | LLM verdict | Yes | After parallel fan-in |

---

## Adding a New Agent

### To the Discovery Pipeline

1. Add the filter function to `agents/decision_support/tools.py`
2. Add a new step in `agents/decision_support/stream.py` (follow the existing pattern: `step_start` → call function → emit `step_log` per message → `step_complete`)
3. Add the step to `pipelineSteps` in `trading-agent.component.ts` with an `id`, `agentName`, and `agentRole`

### To the Chat System

1. Create `agents/workers/my_agent.py` and call `register_agent(name, description, tools=[...])`
2. Import the file in `agents/supervisor.py` to trigger self-registration
3. The supervisor will automatically route to it based on the description you provide

### To the Deep Analysis Graph

1. Create a node function in `agents/workers/`
2. Import and add it to the graph in `agents/analysis_graph.py`
3. Wire it with `graph.add_edge(START, "my_node")` and `graph.add_edge("my_node", "synthesizer")`
4. Update `_synthesizer_node` to include the new agent's result in the LLM prompt
