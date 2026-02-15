# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

CogniCap is a full-stack trading portfolio dashboard that connects to Zerodha's Kite API. It provides real-time portfolio visualization, P&L tracking, stock health analysis, and AI-powered chat using Google Gemini.

## Build & Run Commands

### Both servers (recommended)
```bash
./start.sh   # Starts backend and frontend concurrently
```

### Backend (Flask on :5000)
```bash
cd backend && source venv/bin/activate && python3 app.py
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
# Single test file:
python -m pytest test_stock_health.py
```

## Architecture

**Backend:** Python Flask (`backend/app.py`) — 20+ REST endpoints under `/api/` for auth, portfolio, stock analysis, market data, and chat. Uses KiteConnect SDK for Zerodha API, Google Gemini for AI analysis.

**Frontend:** Angular 18 with standalone components, Angular Material, SCSS. Communicates with backend via `HttpClient` in `kite.service.ts` and `chat.service.ts`.

**Auth flow:** OAuth via Zerodha → user copies `request_token` → backend exchanges for `access_token` → token saved to `backend/access_token.json` (valid one trading day). Route protection via `auth.guard.ts`.

**Data persistence:** JSON files (no database). `analysis_storage.json` caches stock analysis results. `access_token.json` stores session tokens.

### Key Backend Files
- `backend/app.py` — Main Flask server, all API endpoints
- `backend/stock_analyzer.py` — On-demand stock analysis (ADX, EMA, RSI)
- `backend/stock_health_service.py` — Health score calculation

### Key Frontend Paths
- `frontend/cognicap-app/src/app/components/` — 6 standalone components (login, dashboard, chat, health, market, market-banner)
- `frontend/cognicap-app/src/app/services/kite.service.ts` — All backend API calls
- `frontend/cognicap-app/src/app/services/chat.service.ts` — Chat session management
- `frontend/cognicap-app/src/app/guards/auth.guard.ts` — Route protection
- `frontend/cognicap-app/src/app/app.routes.ts` — Routes: `/login`, `/dashboard`

## Environment Variables

Required in `.env` at project root:
- `KITE_API_KEY` / `KITE_API_SECRET` — Zerodha API credentials
- `GEMINI_API_KEY` — Google Gemini API key

## Key Conventions
- Angular uses standalone components (no NgModules)
- TypeScript strict mode is enabled
- Backend API endpoints are grouped: `/api/auth/`, `/api/portfolio/`, `/api/market/`, `/api/chat/`, `/api/analyze-*`
- Frontend auto-refreshes portfolio every 15s and market data every 30s
- Stock analysis is on-demand (not batch-loaded), results cached in `analysis_storage.json`
