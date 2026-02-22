# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

CogniCap is a full-stack trading portfolio dashboard that connects to Zerodha's Kite API. It provides real-time portfolio visualization, P&L tracking, stock health analysis, AI-powered chat using Google Gemini, a paper trading simulator, and a 4-2-1-1 stock selection decision support pipeline.

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
│   ├── decision_support.py # /api/decision-support/run
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
│   ├── config.py           # LLM factory (Gemini + OpenAI fallback)
│   ├── analysis_graph.py   # Scatter-gather analysis workflow
│   ├── analysis_stream.py  # SSE streaming for analysis
│   ├── workers/            # Specialist agents (stats, company_health, breaking_news, general, portfolio)
│   ├── tools/              # Agent tools (portfolio, market, analysis)
│   └── decision_support/   # 4-2-1-1 pipeline (stream.py, tools.py, strategy_config.py)
│
├── stock_analyzer.py       # On-demand stock analysis (used by agents)
├── stock_health_service.py # Portfolio health reports (legacy, uses yfinance)
│
└── data/
    ├── nifty500.csv        # Nifty 500 stock list
    ├── sector_indices.json # Sector-to-index mapping
    └── state/              # Runtime state files (gitignored)
        ├── access_token.json
        ├── analysis_storage.json
        ├── simulator_data.json
        └── simulator_price_history.json
```

**Frontend:** Angular 18 with standalone components, Angular Material, SCSS. Communicates with backend via `HttpClient` in `kite.service.ts`, `chat.service.ts`, and `simulator.service.ts`.

**Auth flow:** OAuth via Zerodha → user copies `request_token` → backend exchanges for `access_token` → token saved to `backend/data/state/access_token.json` (valid one trading day). Route protection via `auth.guard.ts`.

**Data persistence:** JSON files in `backend/data/state/` (gitignored). No database.

### Key Design Patterns
- **Broker Abstraction:** All Kite API calls go through `broker/` — switch brokers by implementing `BrokerAdapter`
- **Blueprint Decomposition:** Each route domain is a Flask Blueprint in `routes/`
- **Service Layer:** Business logic in `services/` has no Flask dependencies — pure Python functions
- **Centralized Config:** All env vars in `config.py`, all magic numbers in `constants.py`

### Key Frontend Paths
- `frontend/cognicap-app/src/app/components/` — 7 standalone components (login, dashboard, chat, health, market, market-banner, trading-agent)
- `frontend/cognicap-app/src/app/services/kite.service.ts` — Portfolio/market API calls
- `frontend/cognicap-app/src/app/services/chat.service.ts` — Chat session management
- `frontend/cognicap-app/src/app/services/simulator.service.ts` — Virtual trading simulator
- `frontend/cognicap-app/src/app/guards/auth.guard.ts` — Route protection
- `frontend/cognicap-app/src/app/app.routes.ts` — Routes: `/login`, `/dashboard`, `/trading-agent`

## Environment Variables

Required in `.env` at project root:
- `KITE_API_KEY` / `KITE_API_SECRET` — Zerodha API credentials
- `GEMINI_API_KEY` — Google Gemini API key
- `OPENAI_API_KEY` — (optional) OpenAI fallback for LLM calls

## Key Conventions
- Angular uses standalone components (no NgModules)
- TypeScript strict mode is enabled
- Backend uses Flask Blueprints — one file per route domain under `routes/`
- All broker API calls go through `broker/` abstraction, never direct `KiteConnect`
- Technical indicators are pure functions in `services/technical.py`
- Frontend auto-refreshes portfolio every 15s and market data every 30s
- Stock analysis is on-demand (not batch-loaded), results cached in `backend/data/state/analysis_storage.json`
- Runtime state files live in `backend/data/state/` (gitignored)
