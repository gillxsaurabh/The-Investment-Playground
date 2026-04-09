# CogniCap — Technical Audit Report
**Date:** 2026-04-07  
**Scope:** Backend agents, pipelines, security, infrastructure, and business profitability gaps  
**Audited by:** Claude Code (claude-sonnet-4-6)

---

## 1. Caching Layer

### Status: IN-MEMORY MODULE GLOBALS — NO REDIS, NO TTL

| Check | Finding |
|---|---|
| Cache key structure | Module-level Python dicts keyed by `instrument_token` (OHLCV), `universe_name` (CSVs), `symbol` (sector map) |
| TTL strategy | **None.** Caches are cleared once per pipeline run via `clear_session_cache()` |
| Cache invalidation | No market-open (9:15am IST) trigger. Invalidation is manual / per pipeline run |
| Cache storage | In-memory Python module globals (`backend/agents/shared/data_infra.py:27–32`) |
| LLM output caching | **None.** Every LLM call hits the API fresh |

### Details

**What's cached:**
```
_session_cache       dict[int, DataFrame]   — OHLCV data keyed by instrument_token
_nifty_cache         Optional[DataFrame]    — Nifty 50 history
_sector_index_cache  dict[str, DataFrame]   — sector indices (FSE, AUTO, PHARMA, …)
_instrument_map      dict[str, int]         — symbol → token
_universe_cache      dict[str, DataFrame]   — CSV universes (nifty100/500/midcap/smallcap)
_symbol_sector_map   dict[str, dict]        — symbol → {sector, sector_index}
```
Source: `agents/shared/data_infra.py:27–32`

**Cache lifecycle:**
- `clear_session_cache()` called at the start of every pipeline run (buy: `tools.py:95`, sell: `sell_stream.py`)
- Universe CSV cache (`_universe_cache`) persists across runs and is never invalidated
- No TTL; no Redis; no Memcached

**Critical flaw — concurrent user corruption:**  
Because caches are module-level globals, two users running the pipeline simultaneously will share and corrupt each other's cache. User B calling `clear_session_cache()` mid-run wipes User A's in-flight data.

**LLM cost note:**  
With zero LLM caching, every pipeline run that calls `ai_rank_stocks()` (tools.py) or the sell scoring engine (sell_tools.py) incurs a full API call. At scale this becomes the dominant cost line.

### Recommendations
- **P0:** Move `_session_cache`, `_nifty_cache`, `_sector_index_cache` to a request-scoped context object instead of module globals. This fixes multi-user correctness immediately.
- **P1:** Add Redis (or Valkey) as shared cache. Keys: `kite:ohlcv:{token}:{date}` (TTL = until next trading day), `screener:{symbol}:ratios` (TTL = 6 h), `llm:conviction:{symbol}:{pipeline_version}:{date}` (TTL = 24 h).
- **P2:** Add a market-open cache flush at 9:15am IST (hook it to the existing APScheduler).

---

## 2. Kite API Usage

### Status: BASIC — NO QUEUE, PLAINTEXT TOKENS, LIMITED ORDER SAFEGUARDS

| Check | Finding |
|---|---|
| Rate limit handling | Fixed `time.sleep(0.35)` delays between calls; no queue, no circuit breaker |
| Single account risk | Platform uses one `KITE_API_KEY`; each user has their own session token stored in DB |
| User Kite token storage | **Plaintext in SQLite** (`user_broker_tokens.access_token`) |
| Token refresh | Not implemented; manual re-link required when token expires |
| Order execution safeguards | Mode-level confirmation (live vs. paper toggle); **no per-order confirmation step** |

### Details

**Rate limiting:**  
`constants.py:66` defines `KITE_API_DELAY = 0.2s`. Multi-threaded `ThreadPoolExecutor` calls in `tools.py` run concurrent fetches with a 0.35s sleep per worker, but there is no global semaphore capping total concurrent Kite requests. Under a large universe scan (Nifty 500), multiple workers will fire Kite calls near-simultaneously.

**Token storage (security risk):**  
```python
# auth_service.py:323–350
INSERT INTO user_broker_tokens (user_id, broker, access_token, ...)
VALUES (...)
```
Kite `access_token` stored in plaintext. Compare this to LLM keys, which are Fernet-encrypted before storage (`llm_key_service.py:36`). This inconsistency is a high-priority security gap.

**No auto-refresh:**  
Kite tokens are daily session tokens that expire at EOD. There is no automatic re-authentication flow. When a token expires, all `@require_broker` endpoints will fail with 401 until the user manually re-links.

**Pre-trade risk checks (positive):**  
`risk_manager.py:29–65` validates: market hours (9:15–15:30 IST), max order value, max position size %, and max open positions before any live trade fires.

**Order confirmation gap:**  
Live mode toggle requires `confirm=true` (`routes/trading.py:43–48`), but individual trade execution (`/api/trading/execute`) places the order directly. Automation trades in `weekly_trader.py:425+` also fire without a confirmation prompt.

### Recommendations
- **P0:** Encrypt Kite `access_token` at rest using the same Fernet approach already implemented for LLM keys in `llm_key_service.py`.
- **P1:** Implement a `TokenRefreshService` that re-runs Kite's session flow at EOD or on 403 errors.
- **P1:** Add a global `asyncio.Semaphore` or `ThreadPoolExecutor` with a max of 3–5 concurrent Kite connections to respect Kite's undocumented rate limits.
- **P2:** Per-order confirmation payload (especially for live mode) to prevent accidental automation trades.

---

## 3. AI Agent Architecture

### Status: WELL-MODULARISED PIPELINE — MISSING PROMPT VERSIONING AND SCHEMA VALIDATION

| Check | Finding |
|---|---|
| Agent definitions | Modular, scoped: 7-stage buy funnel + 5-stage sell pipeline |
| Prompt versioning | **None.** Prompts hardcoded in `tools.py` and `sell_tools.py` |
| BYO LLM integration | Centralized `get_llm()` factory with BYOK support (`agents/config.py:121–196`) |
| Error handling | Graceful fallback to rule-based scores if LLM fails (`tools.py:603–628`, `sell_tools.py:241–248`) |
| Hallucination guardrails | JSON parsing with fallback defaults; **no schema validation** |

### Details

**Pipeline structure (modular — positive):**
```
Buy Pipeline (tools.py):
  1. filter_market_universe()   — volume, EMA-200, relative strength
  2. analyze_technicals()       — RSI, ADX, EMA-20/50
  3. check_fundamentals()       — ROE, D/E, profit growth via Screener.in
  4. check_sector_health()      — 5-day sector index performance
  5. compute_composite_scores() — weighted scoring (0–100)
  6. ai_rank_stocks()           — LLM conviction ranking + extended thinking
  7. rank_final_shortlist()     — portfolio ranker LLM

Sell Pipeline (sell_tools.py):
  1. Portfolio Inspector     — fetch all holdings + resolve tokens
  2. Quant Analyst           — RSI, ADX, EMA-20/50/200, ATR, 3M relative strength
  3. Fundamentals Analyst    — quarterly profit trends, ROE, D/E
  4. Sector Monitor          — 5-day sector performance
  5. Sell Signal Engine      — urgency scoring (0–100, HOLD/WATCH/SELL/STRONG SELL)
```

**LLM factory (positive):**  
All LLM instantiation goes through `agents/config.py:get_llm()`. Supports Claude (default), OpenAI. Per-user BYOK keys resolved before falling back to platform env keys. Never instantiated directly in route files.

**Prompt versioning (gap):**  
Prompts are multi-line f-strings hardcoded in Python. If the prompt changes, the LLM cache (once added) must be invalidated, but there is no version tag or prompt hash to key against. A schema change in the conviction scoring prompt will silently change output behavior.

**Output validation (gap):**  
```python
# tools.py:617–626
try:
    result = json.loads(llm_response)
except:
    conviction_score = 50  # default fallback
```
No schema validation (e.g., Pydantic, jsonschema) on LLM outputs. If the model returns a valid JSON with wrong field names, the fallback silently returns 50 for all stocks — corrupting the ranking without alerting anyone.

**Extended thinking:**  
Claude's extended thinking is used correctly: `temperature=1.0` forced when `extended_thinking=True` (`agents/config.py:76`). Thinking budget: 10,000 tokens for conviction, 5,000 for synthesis (`constants.py:97–98`).

### Recommendations
- **P1:** Add prompt versioning — store prompts in versioned YAML files (`agents/prompts/v1/conviction.yaml`). Include version string in LLM cache keys (when cache is added).
- **P1:** Add Pydantic output models for all LLM JSON outputs. Validate before consuming; log schema mismatches as warnings.
- **P2:** Add a guardrail layer that checks conviction scores for statistical outliers (e.g., all stocks scoring within 5 points of each other indicates a degenerate LLM response).
- **P2:** Wire Sentry (already in deps) to capture LLM fallback events with the raw response for debugging.

---

## 4. Data Pipeline

### Status: SCREENER.IN SCRAPING IS BRITTLE — NO MULTI-VERSION SUPPORT

| Check | Finding |
|---|---|
| Fundamental data source | Screener.in HTML scraping (BeautifulSoup regex) — single source, no fallback |
| Data freshness tracking | Timestamps on `scans`, `stock_analyses`, `trades`, `snapshots` tables |
| Pipeline versioning | Single version; concurrent pipeline runs share global cache |
| Risk bucket application | Via `strategy_config.py` gear presets (not per-stock risk scoring) |

### Details

**Screener.in scraping fragility:**  
```python
# services/fundamentals.py:37–63
def _extract_ratio(html_text, ratio_name):
    # regex on raw HTML text — breaks if Screener.in changes layout
```
The scraper searches for ratio labels (ROE, D/E, Sales Growth) in raw HTML text. Any layout change to Screener.in's tables will silently return `None` for all fundamentals, causing `check_fundamentals()` to skip fundamental scoring — stocks pass with effectively zero fundamental weighting.

There is no fallback data source (e.g., TickerTape API, NSEIndia, or Yahoo Finance) if Screener.in is down or returns a CAPTCHA.

**Timestamp tracking (adequate for now):**  
- `stock_analyses.analyzed_at`, `scans.started_at/completed_at`, `trades.entry_time/exit_time` are stored.
- However, `datetime.now()` is used without explicit timezone (`datetime.now(tz=IST)` not enforced uniformly). This can cause DST confusion if server timezone changes.

**Concurrent pipeline safety (critical gap):**  
Global `_session_cache` means two simultaneous pipeline runs corrupt each other (see Caching section). There is no pipeline version concept — you cannot run v1 (old scoring weights) and v2 (new weights) simultaneously for A/B testing.

**Gear-based risk application (adequate):**  
`strategy_config.py` defines 5 gears (Fortress → Turbo) with different RSI limits, EMA periods, turnover floors, and fundamental check toggles. Risk "bucket" is a gear selection at run time, not a per-stock dynamic score — which is fine for the current design but limits personalization.

### Recommendations
- **P0:** Add a circuit breaker around `scrape_screener_ratios()`. If 3+ consecutive failures occur, mark Screener.in as DOWN and fall back to cached fundamentals (last known good values from `stock_analyses` table).
- **P1:** Add a secondary fundamentals source (TickerTape JSON API, or NSEIndia) as a hot standby.
- **P1:** Normalize all `datetime.now()` calls to `datetime.now(timezone.utc)` or explicit IST (`pytz.timezone("Asia/Kolkata")`).
- **P2:** Isolate pipeline session state per-request so different gears (or A/B prompt tests) can run simultaneously.

---

## 5. Security

### Status: JWT + BCRYPT SOLID — KITE TOKENS UNENCRYPTED, RATE LIMITING WEAK

| Check | Finding |
|---|---|
| Kite token storage | **Plaintext in SQLite** — high severity |
| LLM key storage | Fernet-encrypted at rest (`llm_key_service.py:36`) |
| BYO LLM keys — client vs. server | **Server-side, encrypted.** Keys never returned in API responses |
| User A → User B trade isolation | Enforced via JWT `user_id` binding + `@require_auth` middleware |
| Rate limiting | Flask-Limiter with IP-based key; default 200/min; login/register 5/min |

### Details

**Kite token plaintext (critical):**  
```python
# auth_service.py:323–350
INSERT INTO user_broker_tokens (user_id, broker, access_token, ...)
```
`access_token` is the Kite session token that authorises real-money trades. It is stored in plaintext. If the SQLite file is exfiltrated, all user brokerage sessions are immediately compromised.

**LLM key encryption (good):**  
LLM keys use Fernet symmetric encryption. The cipher key is derived as `base64(SHA256(LLM_KEY_ENCRYPTION_SECRET))` (`llm_key_service.py:25–29`). However, the fallback is `JWT_SECRET` — if only one secret is configured, compromising `JWT_SECRET` gives access to both JWT forgery AND encrypted LLM keys.

**User isolation (adequate):**  
All protected routes use `@require_auth`, which extracts `user_id` from the JWT (not from request params). Broker tokens are retrieved by `user_id`. There is no path for User A to trigger trades against User B's account via the API.

**Admin scope (minor concern):**  
Admin endpoints authenticate via `is_admin` flag in the users table. Admins have no explicit row-level restriction from querying other users' trades or positions via DB access. No audit log for admin actions.

**Rate limiting weaknesses:**
- Uses `get_remote_address` (IP-based) — all users behind a corporate NAT share one limit bucket
- Default 200/min is very permissive for authenticated endpoints like `/api/decision-support/run` (heavy AI call)
- No per-user rate limiting
- In-memory storage (`memory://`) — limits reset on server restart and don't carry across multiple instances

### Recommendations
- **P0:** Encrypt Kite `access_token` using the Fernet cipher already implemented in `llm_key_service.py`. Reuse `get_cipher()` from that module.
- **P0:** Use a separate `LLM_KEY_ENCRYPTION_SECRET` env var (never fall back to `JWT_SECRET`). These should be independent secrets.
- **P1:** Switch Flask-Limiter to `key_func=lambda: g.current_user["id"]` for authenticated endpoints (per-user rate limiting post-auth).
- **P1:** Move Flask-Limiter storage to Redis (`redis://...`) so limits persist across restarts and servers.
- **P2:** Add an `auth_audit` table: record login, logout, broker-link, password-change, and token-refresh events.
- **P2:** Add explicit rate limits to heavy AI endpoints: `/api/decision-support/run` → 2/minute per user, `/api/analyze-stock-stream` → 5/minute per user.

---

## 6. Infrastructure

### Status: NOT HORIZONTALLY SCALABLE — SINGLE-INSTANCE APSCHEDULER, STATEFUL GLOBALS

| Check | Finding |
|---|---|
| Horizontal scaling | **Breaks.** Module-level Python globals cannot be shared across processes/servers |
| Market hours awareness | `risk_manager.py` enforces 9:15–15:30 IST pre-trade; automation runs 10:00am Mon IST |
| Job scheduling | APScheduler BackgroundScheduler — single instance only |
| Logging / audit trail | Structured JSON logging; request_id + user_id on every log line; trade table in SQLite |

### Details

**Why horizontal scaling breaks today:**
```
agents/shared/data_infra.py:27–32
  _session_cache: dict          # process-local, cleared per pipeline
  _nifty_cache: Optional        # process-local, never evicted
  _instrument_map: Optional     # process-local
  _universe_cache: dict         # process-local, never evicted
```
Each Python process has its own copy of these globals. With 2+ Gunicorn workers or 2+ servers, one user's `clear_session_cache()` does not affect another worker's cache. However, universe CSVs loaded in worker 1 are not available in worker 2 until that worker loads them independently. More critically: if a pipeline run is split across multiple requests routed to different workers (e.g., via SSE reconnect), state is inconsistent.

The simulator also reads/writes a shared JSON file (`simulator_data.json`) using `atomic_json_write()` — file-level locking prevents corruption on a single machine, but does not work across multiple servers.

**APScheduler (single-instance gap):**  
```python
# automation/scheduler.py:26–56
scheduler = BackgroundScheduler(timezone="Asia/Kolkata")
scheduler.add_job(run_weekly_automation, 'cron', day_of_week='mon', hour=10)
```
With 2+ server instances, every instance runs `run_weekly_automation()` on Monday 10am. This fires duplicate buy-pipeline runs and places duplicate trades.

**Market hours (adequate):**  
`risk_manager.py` correctly gates live trades to 9:15–15:30 IST. Automation fires at 10:00am IST (after opening auction). NSE holiday logic (`nse_holidays.py`) is imported but used only for stall-exit day counting — not for preventing automation on holidays.

**Logging (good foundation):**  
Structured logging with JSON format option, request_id propagation, and user_id on every log line (`logging_config.py`). Trade lifecycle is captured in the `trades`, `position_snapshots`, and `account_snapshots` SQLite tables.

**Gaps in audit trail:**
- No log of authentication events (login, logout, password change, broker-link)
- No log of order modifications or cancellations
- `account_snapshots` captures balance changes but not the cause (which trade, which automation run)

### Recommendations
- **P0:** Move all module-level pipeline caches to a request-scoped object passed explicitly through the pipeline call stack (zero external dependency — just refactor `data_infra.py`).
- **P0:** Add distributed locking to APScheduler (use APScheduler's `SQLAlchemyJobStore` or a Redis lock via `redis-py`) so only one server runs the weekly job.
- **P1:** Integrate Redis as the single shared cache store for all data fetched per pipeline run.
- **P1:** Add NSE holiday check in `scheduler.py` before firing the weekly automation — skip to next trading day if Monday is a holiday.
- **P2:** Migrate simulator state from JSON files to the SQLite DB (already used for trades) to support multi-worker deployments.
- **P2:** Add structured audit log entries for: authentication events, broker link/unlink, automation trigger, trade placed/closed.

---

## 7. Business Profitability Gaps

### P1 Conversion: Discoverers Don't Pay

**Current state:** Users can browse analysis and discovery features without connecting Kite.  
**Problem:** Zero monetization surface for the broad top-of-funnel.

**What changes it:**  
- Paper trading simulator is already built. Make it the primary "try before you connect" loop.
- Enforce a weekly-automation trial with simulated trades, then show the user a "your portfolio would have gained X%" card after 2–3 weeks.
- Gate the real-money Kite connection (and live automation) behind a paid tier.
- Track the conversion funnel explicitly: anonymous → registered → paper-active → kite-linked → paid.

**Technical pre-requisites:**  
- Simulator isolation per user (currently all users share one `simulator_data.json` — already flagged in SaaS hardening work).
- Onboarding flow that auto-creates a paper portfolio seeded with a demonstration watchlist.

---

### LLM Cost: Platform Bears Cost for Non-BYO Users

**Current state:** Platform uses `ANTHROPIC_API_KEY` / `GEMINI_API_KEY` for all users who haven't configured BYOK.  
**Problem:** Every sell-pipeline run triggers a Claude extended-thinking call (10K token budget). At $15/M tokens, a 20-stock portfolio audit costs ~$0.15–0.30 per run.

**What changes it:**
1. **Instrument LLM cost tracking now.** Log `user_id`, `pipeline`, `provider`, `input_tokens`, `output_tokens`, `cost_usd` to a `llm_usage` table on every LLM call. The `get_llm()` factory in `agents/config.py` is the right place to add this hook.
2. **Define cost per tier:** Free tier → LLM calls limited (e.g., 3 sell audits/month). Pro tier → unlimited or BYOK required.
3. **Cache LLM outputs** with a 24-hour TTL (stock conviction for a given date is unlikely to change). Every cache hit is direct cost savings.

**Estimated break-even:** At $10/user/month, one user who runs sell pipeline daily costs ~$9/month in LLM alone. Margins are near-zero unless BYOK or caching is mandatory at scale.

---

### Cache Efficiency: Unknown Hit Rate

**Current state:** No cache (see Section 1). Every pipeline run fetches everything fresh.  
**Problem:** Kite OHLCV data, Screener.in fundamentals, and LLM conviction calls are all repeated on every run even if underlying data hasn't changed since market open.

**What changes it:**
- Implement Redis caching with distinct TTLs: OHLCV (until next trading day), fundamentals (6h), LLM output (24h).
- Instrument cache hit/miss rates from day one using a counter in each cache wrapper.
- Report cache hit rate in the `/health` endpoint so it's visible in monitoring.
- Target: >80% cache hit rate on repeat analysis of the same watchlist within a trading day.

---

### Churn in Bear Market

**Current state:** Core value proposition (discover undervalued stocks, automate buys) is weakest when the market is down.  
**Problem:** Bear markets increase churn because users don't see wins from the automation.

**What changes it:**
- **Portfolio Health Score** (already partially built in `stock_health_service.py`) — surface this prominently as a standalone feature. A health dashboard is useful at any market phase.
- **Sell audit pipeline** (System 2) is actually *more* valuable in a bear market. Reframe the sell pipeline as "protect your capital" messaging, not just "find exits."
- **Drawdown analysis:** Show each position's max drawdown, current drawdown vs. historical average. This gives users actionable insight even when no trades are firing.
- **Bear-mode automation:** Add a Fortress gear (Gear 1) that auto-activates when Nifty 50 is below its 200-day EMA. This shifts automation to capital-preservation mode, giving users a reason to stay subscribed.

---

### P3 Near-Zero Revenue

**Current state:** No monetization of platform features independent of LLM usage.  
**Problem:** LLM usage fees scale with user activity; platform features (alerts, automation rules, export) have zero marginal cost.

**What changes it:**
- **Alerts engine:** Price alerts, RSI alerts, and sell-score threshold alerts have zero LLM cost. Gate >3 active alerts behind paid tier.
- **Automation rules:** Custom gear scheduling (e.g., "run Turbo gear every Monday, Balanced every Wednesday") is a platform capability, not an LLM capability. Charge for it.
- **Data export:** CSV/PDF export of audit results and portfolio history. Trivial to implement; high perceived value to users who use spreadsheets.
- **Portfolio benchmarking:** "Your portfolio vs. Nifty 100" is computable from existing data. No LLM cost. High retention value.

---

### No Network Effects

**Current state:** Users operate in complete isolation. No shared signal, no community layer.  
**Problem:** Single-player financial tools commoditise quickly. No switching cost.

**What changes it:**
- **Community benchmarking:** "Top 10% of CogniCap portfolios returned X% this month" — anonymised aggregate stats from `account_snapshots`. No new data needed; just aggregation queries.
- **Scan popularity signal:** When multiple users' pipelines converge on the same stock, that convergence itself is a signal. Surface "trending in CogniCap" as a soft social proof layer.
- **Shared watchlists:** Allow users to publish (opt-in) their active discovery watchlists. Follower count creates lock-in.

**Technical pre-requisites:**
- Opt-in consent layer (GDPR-compliant).
- Aggregation queries on `scans` and `scan_candidates` tables (schema already has `scan_id` → `scan_candidates.stock_symbol`).

---

## Summary Scorecard

| Area | Status | Priority Gaps |
|---|---|---|
| Caching | ⚠️ RISKY | No Redis; module globals corrupt multi-user runs; zero LLM caching |
| Kite API | ⚠️ BASIC | Tokens stored plaintext; no auto-refresh; no per-order confirmation |
| AI Agents | ✅ GOOD | No prompt versioning; no Pydantic output validation |
| Data Pipeline | ⚠️ BRITTLE | Screener.in scraping single point of failure; concurrent runs unsafe |
| Security | ⚠️ MIXED | Kite tokens plaintext (critical); LLM keys encrypted; rate limiting IP-based only |
| Infrastructure | ❌ NOT SCALABLE | Module globals break multi-server; APScheduler not distributed; simulator in JSON files |

### P0 Action Items (Production Blockers)
1. Encrypt Kite `access_token` using `llm_key_service.py`'s `get_cipher()` — `auth_service.py:323`
2. Move pipeline caches from module globals to request-scoped context — `data_infra.py:27–32`
3. Add distributed lock to APScheduler weekly job — `automation/scheduler.py:31–39`
4. Use separate `LLM_KEY_ENCRYPTION_SECRET` env var independent of `JWT_SECRET`

### P1 Action Items (Pre-Launch)
5. Add Redis as shared cache layer; TTL: OHLCV 1-day, fundamentals 6h, LLM 24h
6. Screener.in circuit breaker with fallback to last-known-good fundamentals from DB
7. Per-user rate limiting on heavy AI endpoints (post-auth key function in Flask-Limiter)
8. LLM usage cost tracking table (`llm_usage`) — hook into `get_llm()` factory
9. Pydantic output validation on all LLM JSON responses
10. NSE holiday check before firing automation
