# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

CogniCap is a full-stack trading portfolio dashboard that connects to Zerodha's Kite API. It provides real-time portfolio visualization, P&L tracking, stock health analysis, AI-powered chat, a paper trading simulator, a 4-2-1-1 stock discovery pipeline (buy), a portfolio sell-audit pipeline, and a weekly automation system.

## Build & Run Commands

### Both servers (recommended)
```bash
./start.sh   # Starts backend and frontend concurrently
```

### Backend (Flask on :5000)
```bash
cd backend && ./venv/bin/python3 app.py
```

### Frontend (Angular on :4200)
```bash
cd frontend/cognicap-app && ng serve
```

### Build frontend
```bash
cd frontend/cognicap-app && ng build
```

### Run frontend tests
```bash
cd frontend/cognicap-app && ng test
```

### Run backend tests
```bash
cd backend && source venv/bin/activate && python -m pytest test_*.py
```

## Architecture

### Backend Structure (Modular)

The backend follows separation of concerns with 4 layers:

```
backend/
├── app.py                  # Slim entry point (~30 lines): create_app() factory
├── config.py               # Centralized env vars, file paths, Flask settings
├── constants.py            # All magic numbers (indicator periods, weights, thresholds)
├── logging_config.py       # Structured logging setup
│
├── broker/                 # Broker abstraction layer (adapter pattern)
│   ├── base.py             # Abstract BrokerAdapter ABC
│   ├── kite_adapter.py     # KiteConnect implementation
│   └── __init__.py         # get_broker(access_token) factory
│
├── routes/                 # Flask Blueprints (one per domain)
│   ├── auth.py             # /api/auth/* (login, authenticate, verify)
│   ├── portfolio.py        # /api/portfolio/* (holdings, positions, summary, top-performers, health-report)
│   ├── market.py           # /api/market/* (indices, top-stocks)
│   ├── analysis.py         # /api/analyze-* (stock, stock-stream, all)
│   ├── chat.py             # /api/chat/* (send, clear)
│   ├── trade.py            # /api/trade/* (funds, calculate-exits)
│   ├── simulator.py        # /api/simulator/* (execute, positions, close, reset, status, price-history)
│   ├── decision_support.py # /api/decision-support/run (buy pipeline)
│   ├── automation.py       # /api/automation/* (status, enable, run-now, history)
│   └── health.py           # /health
│
├── services/               # Business logic (no Flask, no HTTP)
│   ├── technical.py        # Pure functions: ADX, EMA, RSI, ATR calculations
│   ├── fundamentals.py     # Screener.in scraping and scoring
│   ├── analysis_storage.py # JSON-based analysis cache CRUD
│   ├── market_data.py      # Simulation fallback data
│   └── simulator_engine.py # PaperTradingSimulator class
│
├── agents/                 # LangGraph-based multi-agent system
│   ├── supervisor.py       # Routes messages to workers
│   ├── config.py           # LLM factory: get_llm(provider="claude"|"gemini"|"openai")
│   ├── analysis_graph.py   # Scatter-gather analysis workflow
│   ├── analysis_stream.py  # SSE streaming for analysis
│   ├── workers/            # Specialist agents (stats, company_health, breaking_news, general, portfolio)
│   ├── tools/              # Agent tools (portfolio, market, analysis)
│   └── decision_support/   # 4-2-1-1 pipelines
│       ├── stream.py           # SSE streaming for buy pipeline
│       ├── tools.py            # Buy pipeline filter functions (5 agents)
│       ├── sell_stream.py      # SSE streaming for sell pipeline
│       ├── sell_tools.py       # Sell pipeline enrichment + scoring functions
│       └── strategy_config.py  # STRATEGY_GEARS config (gear 1-5 parameters)
│
├── automation/             # Weekly Monday automation orchestrator
│   ├── scheduler.py        # APScheduler: fires run_weekly_automation() Mon 9AM IST
│   ├── weekly_trader.py    # Multi-gear pipeline runner; executes simulator trades
│   └── nse_holidays.py     # NSE trading calendar helper
│
├── stock_analyzer.py       # On-demand stock analysis (used by agents)
├── stock_health_service.py # Portfolio health reports (legacy, uses yfinance)
│
└── data/
    ├── nifty100.csv        # Nifty 100 universe
    ├── nifty500.csv        # Nifty 500 universe
    ├── nifty_midcap150.csv # Midcap 150 universe
    ├── nifty_smallcap250.csv # Smallcap 250 universe
    ├── sector_indices.json # Sector-to-index mapping
    └── state/              # Runtime state files (gitignored)
        ├── access_token.json
        ├── analysis_storage.json
        ├── simulator_data.json
        ├── simulator_price_history.json
        ├── automation_state.json
        └── cognicap.db         # SQLite — trade lifecycle (see db.md)
```

**Frontend:** Angular 18 with standalone components, Angular Material, SCSS. Communicates with backend via `HttpClient` in `kite.service.ts`, `chat.service.ts`, and `simulator.service.ts`.

**Auth flow:** OAuth via Zerodha → user copies `request_token` → backend exchanges for `access_token` → token saved to `backend/data/state/access_token.json` (valid one trading day). Route protection via `auth.guard.ts`.

**Data persistence:** JSON files + SQLite in `backend/data/state/` (gitignored). See `db.md` for the full SQLite schema (6 tables: scans, scan_candidates, stock_analyses, trades, position_snapshots, account_snapshots).

### Key Design Patterns
- **Broker Abstraction:** All Kite API calls go through `broker/` — switch brokers by implementing `BrokerAdapter`
- **Blueprint Decomposition:** Each route domain is a Flask Blueprint in `routes/`
- **Service Layer:** Business logic in `services/` has no Flask dependencies — pure Python functions
- **Centralized Config:** All env vars in `config.py`, all magic numbers in `constants.py`

### LLM Factory (`agents/config.py`)

Use `get_llm(provider=..., temperature=..., extended_thinking=..., thinking_budget=...)`:
- `provider="claude"` → Claude claude-sonnet-4-6 via `ANTHROPIC_API_KEY`. Supports `extended_thinking=True` (forces temperature=1.0 per Anthropic requirement).
- `provider="gemini"` / `None` → Gemini 2.5 Flash with automatic OpenAI fallback.
- `provider="openai"` → GPT-4o-mini directly.

**Claude is the default for sell pipeline and conviction scoring.** The buy pipeline's AI Conviction Engine (Agent 5) uses Gemini. Chat agents use Gemini.

### Agent Systems

**System 1 — Stock Discovery (Buy) Pipeline** (`/api/decision-support/run`):
Sequential 5-agent funnel: Market Scanner → Quant Analyst → Fundamentals Analyst → Sector Momentum → AI Conviction Engine. Filters Nifty universe (gear-dependent) down to 3–5 ranked stocks. See `AGENTS.md` for full details.

**System 2 — Sell Audit Pipeline** (`/api/decision-support/sell`):
Analyzes ALL portfolio holdings for sell urgency — no filtering, every holding is scored. 5-stage pipeline:
1. Portfolio Inspector — fetch live holdings + resolve instrument tokens + sector lookup
2. Quant Analyst — RSI, ADX, EMA-20/50/200, ATR, 3M relative strength (parallel via ThreadPoolExecutor)
3. Fundamentals Analyst — quarterly profit trends, ROE, D/E from Screener.in (parallel, 3 workers)
4. Sector Monitor — 5-day sector index performance
5. Sell Signal Engine — urgency scoring (0–100, HOLD/WATCH/SELL/STRONG SELL) + Claude AI reasoning with extended thinking

**System 3 — Chat & Deep Analysis** (`/api/chat/*`, `/api/analyze-*`):
Supervisor-routed LangGraph graph. See `AGENTS.md` for agent details.

**Weekly Automation** (`backend/automation/`):
Runs every Monday at 9AM IST via APScheduler. Runs buy pipeline across multiple gears (Turbo→Balanced→Growth, fallback to Cautious/Fortress), picks top 2 per gear (deduplicated), targets 6 total active positions, executes via paper simulator. State in `automation_state.json`.

### Key Frontend Paths
- `frontend/cognicap-app/src/app/components/` — standalone components (login, dashboard, chat, health, market, market-banner, trading-agent)
- `frontend/cognicap-app/src/app/services/kite.service.ts` — Portfolio/market API calls
- `frontend/cognicap-app/src/app/services/chat.service.ts` — Chat session management
- `frontend/cognicap-app/src/app/services/simulator.service.ts` — Virtual trading simulator
- `frontend/cognicap-app/src/app/guards/auth.guard.ts` — Route protection
- `frontend/cognicap-app/src/app/app.routes.ts` — Routes: `/login`, `/dashboard`, `/trading-agent`

## Environment Variables

Required in `.env` at project root (or `backend/.env` — backend's takes priority for Kite keys):
- `KITE_API_KEY` / `KITE_API_SECRET` — Zerodha API credentials
- `ANTHROPIC_API_KEY` — Claude API key (required for sell pipeline + conviction scoring)
- `GEMINI_API_KEY` — Google Gemini API key (buy pipeline, chat agents)
- `OPENAI_API_KEY` — (optional) fallback when Gemini hits rate limits

## Key Conventions
- Angular uses standalone components (no NgModules); TypeScript strict mode enabled
- All broker API calls go through `broker/` abstraction, never direct `KiteConnect`
- Technical indicators are pure functions in `services/technical.py`
- Frontend auto-refreshes portfolio every 15s and market data every 30s
- Stock analysis is on-demand (not batch-loaded), results cached in `analysis_storage.json`
- Runtime state files live in `backend/data/state/` (gitignored)
- Claude is the default LLM for sell pipeline AI ranking; Gemini for buy pipeline and chat
- `agents/config.py:get_llm()` is the single entry point for all LLM instantiation — never instantiate LLMs directly in route/service files
- SQLite DB (`cognicap.db`) tracks the full trade lifecycle for retrospective analysis; use `PRAGMA foreign_keys = ON` and `WAL` journal mode (see `db.md` for schema)
