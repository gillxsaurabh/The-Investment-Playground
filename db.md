# CogniCap Database Schema

A systematic record of every action from stock discovery to trade exit, designed for retrospective decision analysis.

---

## Overview

The database captures the complete lifecycle of a trading decision:

```
Scan Run → Stage-by-stage filtering → Shortlist → Trade Entry → Position Monitoring → Trade Exit
```

The goal is to answer questions like:
- Did the discovery pipeline select genuinely good stocks?
- Which filter stage had the most predictive power?
- Was the AI conviction score correlated with actual returns?
- Were stop losses placed optimally (too tight? too loose)?
- Which gear setting performs best over time?
- Was news sentiment a useful signal?

**Engine:** SQLite
**Location:** `backend/data/cognicap.db`
**Schema version:** 1.0

---

## Entity Relationship Overview

```
scans ──────────────────────────── 1:N ── scan_candidates
  │                                             │
  │  (scan_id FK on trade is optional)          │  (all stage data per stock per scan)
  │
trades ─────────────────────────── 1:N ── position_snapshots
  │
  └── references scan_candidates (scan_id + symbol) to link outcomes back

stock_analyses ── (standalone, triggered on-demand, not tied to a scan)

account_snapshots ── (point-in-time account state at key events)
```

---

## Tables

### 1. `scans`

One row per decision-support pipeline run. Records the parameters used and aggregate outcome.

```sql
CREATE TABLE scans (
    -- Identity
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    scan_id         TEXT    NOT NULL UNIQUE,        -- UUID e.g. "scan_20260224_143201_abc123"
    started_at      DATETIME NOT NULL,              -- ISO 8601
    completed_at    DATETIME,
    status          TEXT    NOT NULL DEFAULT 'running',  -- running | completed | failed | cancelled
    error_message   TEXT,                           -- if status = failed

    -- Strategy parameters (what was set for this run)
    gear            INTEGER NOT NULL,               -- 1 (Fortress) to 5 (Turbo)
    gear_label      TEXT    NOT NULL,               -- Fortress | Cautious | Balanced | Growth | Turbo
    universe        TEXT    NOT NULL,               -- nifty100 | nifty500 | nifty_midcap150 | nifty_smallcap250
    min_turnover    REAL    NOT NULL,               -- minimum daily turnover threshold (in Rupees)
    rsi_buy_limit   INTEGER NOT NULL,               -- RSI pullback entry threshold (e.g. 30)
    adx_min         INTEGER NOT NULL,               -- minimum ADX for trend confirmation (e.g. 20)
    trail_multiplier REAL   NOT NULL,               -- ATR trail multiplier (e.g. 1.5)
    fundamental_check TEXT  NOT NULL,               -- strict | standard | loose | none
    sector_5d_tolerance REAL NOT NULL,              -- minimum sector 5d change allowed (e.g. -0.5)
    min_volume_ratio REAL   NOT NULL,               -- 5d/20d volume ratio minimum (e.g. 0.7)

    -- Market regime at time of scan
    vix             REAL,                           -- NSE India VIX value
    market_regime   TEXT,                           -- normal | fearful

    -- Funnel summary (how many stocks passed each stage)
    total_scanned                INTEGER,           -- initial universe size
    universe_filter_passed       INTEGER,           -- after Stage 1: turnover + volume + EMA + RS
    technical_filter_passed      INTEGER,           -- after Stage 2: ADX + RSI triggers
    fundamental_filter_passed    INTEGER,           -- after Stage 3: profit growth / ROE / D/E
    sector_filter_passed         INTEGER,           -- after Stage 4: sector 5d change
    final_selected               INTEGER            -- final shortlist size after AI ranking
);

CREATE INDEX idx_scans_started_at ON scans(started_at);
CREATE INDEX idx_scans_gear ON scans(gear);
```

---

### 2. `scan_candidates`

One row per stock evaluated in a scan. Contains all data produced at every filter stage, including the reason a stock was rejected (if it was). Stocks that make the final shortlist have all fields populated.

```sql
CREATE TABLE scan_candidates (
    -- Identity
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    scan_id         TEXT    NOT NULL REFERENCES scans(scan_id) ON DELETE CASCADE,
    symbol          TEXT    NOT NULL,
    instrument_token INTEGER,
    sector          TEXT,
    sector_index    TEXT,                           -- e.g. NSE:NIFTY AUTO

    -- ── STAGE 1: UNIVERSE FILTER ─────────────────────────────────────────────
    -- (All stocks in the universe start here)
    current_price           REAL,
    avg_volume_20d          REAL,                   -- 20-day average daily volume (shares)
    avg_turnover_20d        REAL,                   -- avg_volume × avg_price (Rupees)
    volume_ratio            REAL,                   -- avg_vol_5d / avg_vol_20d
    ema_200                 REAL,                   -- 200-day EMA at time of scan
    stock_3m_return         REAL,                   -- % return over last 63 trading days
    nifty_3m_return         REAL,                   -- Nifty 50 return over same period
    sector_3m_return        REAL,                   -- sector index return over same period

    passed_universe_filter  BOOLEAN,
    universe_fail_reason    TEXT,                   -- e.g. "below_200_ema", "low_volume_ratio", "underperforms_nifty"

    -- ── STAGE 2: TECHNICAL SETUP ─────────────────────────────────────────────
    -- (Only stocks passing Stage 1 are evaluated here)
    ema_20                  REAL,
    rsi                     REAL,                   -- 14-period RSI (0-100)
    adx                     REAL,                   -- 14-period ADX (0-100)
    rsi_trigger             TEXT,                   -- pullback | momentum

    passed_technical_filter BOOLEAN,
    technical_fail_reason   TEXT,                   -- e.g. "adx_too_low", "no_rsi_trigger"

    -- ── STAGE 3: FUNDAMENTALS ────────────────────────────────────────────────
    -- (Only stocks passing Stage 2 are evaluated here)
    -- Source: Screener.in
    profit_yoy_growing      BOOLEAN,               -- current Q profit > Q-4 profit
    profit_qoq_growing      BOOLEAN,               -- current Q profit > Q-1 profit
    quarterly_profit_growth BOOLEAN,               -- the gate: either YoY or QoQ depending on gear
    roe                     REAL,                   -- Return on Equity (%) — scraped, may be NULL
    debt_to_equity          REAL,                   -- D/E ratio — scraped, may be NULL

    passed_fundamental_filter BOOLEAN,
    fundamental_fail_reason   TEXT,                 -- e.g. "profit_declining", "high_debt", "low_roe"

    -- ── STAGE 4: SECTOR HEALTH ───────────────────────────────────────────────
    sector_5d_change        REAL,                   -- sector index % change over last 5 trading days

    passed_sector_filter    BOOLEAN,
    sector_fail_reason      TEXT,                   -- e.g. "sector_declining"

    -- ── STAGE 5: COMPOSITE SCORING (Rule-Based) ──────────────────────────────
    composite_score         REAL,                   -- 0-100 overall score
    score_technical         REAL,                   -- 0-25: RSI quality + ADX strength + EMA distance
    score_fundamental       REAL,                   -- 0-25: profit growth + ROE quality
    score_relative_strength REAL,                   -- 0-25: outperformance vs Nifty + sector
    score_volume_health     REAL,                   -- 0-25: volume ratio + turnover size

    -- ── STAGE 6: AI RANKING (LLM + News) ─────────────────────────────────────
    ai_conviction           INTEGER,               -- 1-10 (LLM conviction score)
    why_selected            TEXT,                   -- LLM 1-sentence reason (≤ 25 words)
    news_sentiment          INTEGER,               -- 1-5 (1=very negative, 5=very positive)
    news_flag               TEXT,                   -- warning | clear
    news_headlines          TEXT,                   -- JSON array of up to 3 recent headlines

    -- ── STAGE 7: PORTFOLIO RANKER (Final Multi-Factor) ───────────────────────
    final_rank              INTEGER,               -- 1 = best pick
    final_rank_score        REAL,                   -- 0-100 weighted score
    rank_reason             TEXT,                   -- LLM explanation citing top factors

    -- Normalized factor components (each 0-100, min-max within this scan batch)
    rank_factor_conviction_norm   REAL,             -- 35% weight in final score
    rank_factor_composite_norm    REAL,             -- 25% weight
    rank_factor_rs_norm           REAL,             -- 15% weight
    rank_factor_fundamental_norm  REAL,             -- 15% weight
    rank_factor_sector_norm       REAL,             -- 10% weight

    reached_final_shortlist BOOLEAN DEFAULT FALSE,  -- TRUE if this stock made the final ranked list

    UNIQUE (scan_id, symbol)
);

CREATE INDEX idx_scan_candidates_scan_id ON scan_candidates(scan_id);
CREATE INDEX idx_scan_candidates_symbol ON scan_candidates(symbol);
CREATE INDEX idx_scan_candidates_shortlist ON scan_candidates(scan_id, reached_final_shortlist);
```

---

### 3. `stock_analyses`

Results from on-demand single-stock analysis (the 3-agent: Stats + CompanyHealth + BreakingNews).
Separate from scan pipeline — triggered when user clicks "Analyze" on a stock.

```sql
CREATE TABLE stock_analyses (
    -- Identity
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol          TEXT    NOT NULL,
    analyzed_at     DATETIME NOT NULL,
    triggered_by    TEXT,                           -- user | system | scan_followup

    -- Overall weighted score
    overall_score   REAL,                           -- 1-5 weighted: recency×0.25 + trend×0.25 + fund×0.30 + news×0.20

    -- ── STATS AGENT: Recency (Relative Strength vs Nifty) ────────────────────
    recency_score           REAL,                   -- 1-5
    recency_stock_return    REAL,                   -- 90-day stock return %
    recency_nifty_return    REAL,                   -- 90-day Nifty 50 return %
    recency_outperformance  REAL,                   -- stock_return - nifty_return
    recency_detail          TEXT,                   -- e.g. "Strong outperformance: +35.2% vs Nifty +18.1%"

    -- ── STATS AGENT: Trend (ADX + EMA Crossover) ─────────────────────────────
    trend_score             REAL,                   -- 1-5
    trend_adx               REAL,                   -- ADX value at time of analysis
    trend_ema_20            REAL,
    trend_ema_50            REAL,
    trend_strength          TEXT,                   -- Strong | Moderate | Weak
    trend_direction         TEXT,                   -- Bullish | Bearish | Mixed

    stats_explanation       TEXT,                   -- LLM narrative (2-3 sentences)

    -- ── COMPANY HEALTH AGENT: Fundamentals ───────────────────────────────────
    fundamental_score       REAL,                   -- 1-5
    fund_roe                REAL,                   -- Return on Equity %
    fund_debt_to_equity     REAL,                   -- D/E ratio
    fund_sales_growth       REAL,                   -- annual sales growth %
    fundamental_summary     TEXT,                   -- e.g. "ROE: 18.5%, D/E: 0.8, Growth: 12.3%"
    fundamental_explanation TEXT,                   -- LLM narrative (2-3 sentences)

    -- ── BREAKING NEWS AGENT ───────────────────────────────────────────────────
    news_score              REAL,                   -- 1-5
    news_explanation        TEXT                    -- LLM narrative (3-4 sentences)
);

CREATE INDEX idx_stock_analyses_symbol ON stock_analyses(symbol);
CREATE INDEX idx_stock_analyses_analyzed_at ON stock_analyses(analyzed_at);
```

---

### 4. `trades`

One row per virtual trade. Links to the scan that discovered it (if applicable).
Updated in-place as the trade progresses. Final state after exit carries full lifecycle.

```sql
CREATE TABLE trades (
    -- Identity
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    trade_id        TEXT    NOT NULL UNIQUE,        -- SIM_ddmmyy_{SYMBOL}_{random}

    -- Discovery link (optional — NULL if trade entered without running a scan)
    scan_id         TEXT REFERENCES scans(scan_id),
    scan_rank       INTEGER,                        -- rank from the discovery scan (1 = top pick)
    scan_ai_conviction INTEGER,                     -- AI conviction score at time of discovery (1-10)
    scan_composite_score REAL,                      -- composite score at time of discovery (0-100)
    scan_final_rank_score REAL,                     -- weighted final rank score (0-100)
    scan_rsi        REAL,                           -- RSI value at time of discovery
    scan_adx        REAL,                           -- ADX value at time of discovery
    scan_rsi_trigger TEXT,                          -- pullback | momentum (entry type)
    scan_news_flag  TEXT,                           -- warning | clear from scan

    -- Stock info
    symbol          TEXT    NOT NULL,
    instrument_token INTEGER,
    sector          TEXT,

    -- ── ENTRY ─────────────────────────────────────────────────────────────────
    entry_ltp       REAL    NOT NULL,               -- market price when order confirmed
    entry_price     REAL    NOT NULL,               -- actual fill price (ltp + spread)
    quantity        INTEGER NOT NULL,
    total_cost      REAL    NOT NULL,               -- entry_price × quantity
    entry_time      DATETIME NOT NULL,

    -- Risk parameters at entry
    atr_at_entry    REAL    NOT NULL,               -- ATR (14-period, 30-day data) at entry time
    trail_multiplier REAL   NOT NULL,               -- ATR multiplier for stop (gear-dependent)
    initial_sl      REAL    NOT NULL,               -- entry_ltp - (trail_multiplier × atr)
    risk_per_share  REAL    NOT NULL,               -- trail_multiplier × atr
    risk_per_trade  REAL    NOT NULL,               -- risk_per_share × quantity

    -- ── POSITION MONITORING (updated continuously) ────────────────────────────
    highest_price_seen REAL,                        -- all-time high since entry
    last_new_high_date DATE,                        -- date of last all-time high
    current_sl      REAL,                           -- trailing stop (ratchets up, never down)

    -- ── EXIT ──────────────────────────────────────────────────────────────────
    exit_ltp        REAL,                           -- market price at exit
    exit_price      REAL,                           -- actual fill price (ltp - spread)
    exit_time       DATETIME,
    exit_reason     TEXT,                           -- Trailing Stop Hit | Stall Exit | Manual

    -- P&L
    realized_pnl    REAL,                           -- (exit_price - entry_price) × quantity
    realized_pnl_pct REAL,                          -- (exit_price - entry_price) / entry_price × 100
    max_unrealized_pnl REAL,                        -- highest unrealized P&L during holding (derived from snapshots)
    max_unrealized_pnl_pct REAL,                    -- % version

    -- Duration
    holding_days    INTEGER,                        -- calendar days from entry to exit

    -- Status
    status          TEXT    NOT NULL DEFAULT 'OPEN',  -- OPEN | CLOSED

    -- Account context
    gear_at_entry   INTEGER,                        -- which gear was active when trade was placed
    account_balance_before REAL,                    -- cash balance before this trade
    account_balance_after  REAL                     -- cash balance after entry deduction
);

CREATE INDEX idx_trades_symbol ON trades(symbol);
CREATE INDEX idx_trades_scan_id ON trades(scan_id);
CREATE INDEX idx_trades_status ON trades(status);
CREATE INDEX idx_trades_entry_time ON trades(entry_time);
CREATE INDEX idx_trades_exit_reason ON trades(exit_reason);
```

---

### 5. `position_snapshots`

Time-series price snapshots recorded during an open position. Enables charting of the
unrealized P&L curve and after-the-fact analysis of how price moved relative to the stop.

> **Note:** This table grows fast. Each open position generates a row every ~5 seconds.
> For long-held positions, consider purging snapshots older than 30 days or
> downsampling to 1-minute resolution after the trade closes.

```sql
CREATE TABLE position_snapshots (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    trade_id        TEXT    NOT NULL REFERENCES trades(trade_id) ON DELETE CASCADE,
    symbol          TEXT    NOT NULL,
    snapshot_time   DATETIME NOT NULL,

    ltp             REAL    NOT NULL,               -- live traded price at snapshot
    entry_price     REAL    NOT NULL,               -- entry fill price (constant, for reference)
    current_sl      REAL    NOT NULL,               -- trailing stop at this moment
    highest_price_seen REAL NOT NULL,               -- high-water mark at this moment
    unrealized_pnl  REAL    NOT NULL,               -- (ltp - entry_price) × quantity
    unrealized_pnl_pct REAL NOT NULL,               -- %
    quantity        INTEGER NOT NULL
);

CREATE INDEX idx_position_snapshots_trade_id ON position_snapshots(trade_id);
CREATE INDEX idx_position_snapshots_time ON position_snapshots(trade_id, snapshot_time);
```

---

### 6. `account_snapshots`

Point-in-time account state recorded at key events. Provides an equity curve for the simulator.

```sql
CREATE TABLE account_snapshots (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    snapshot_time   DATETIME NOT NULL,
    event_type      TEXT    NOT NULL,               -- trade_open | trade_close | reset | daily_close
    trade_id        TEXT,                           -- associated trade (if applicable)

    initial_capital REAL    NOT NULL,
    current_balance REAL    NOT NULL,               -- liquid cash
    total_realized_pnl REAL NOT NULL,               -- sum of all closed trade P&L
    open_position_cost REAL NOT NULL,               -- capital tied up in open positions
    unrealized_pnl  REAL    NOT NULL,               -- sum of all open position mark-to-market
    net_equity      REAL    NOT NULL,               -- current_balance + open_position_cost + unrealized_pnl

    total_trades    INTEGER NOT NULL,               -- cumulative closed trades
    winning_trades  INTEGER NOT NULL,               -- trades with realized_pnl > 0
    losing_trades   INTEGER NOT NULL                -- trades with realized_pnl ≤ 0
);

CREATE INDEX idx_account_snapshots_time ON account_snapshots(snapshot_time);
CREATE INDEX idx_account_snapshots_event ON account_snapshots(event_type);
```

---

## Key Analytical Queries

These queries answer the most important retrospective questions.

### 1. Did the AI conviction score predict returns?
```sql
SELECT
    t.scan_ai_conviction,
    COUNT(*)                            AS trades,
    ROUND(AVG(t.realized_pnl_pct), 2)  AS avg_return_pct,
    ROUND(AVG(CASE WHEN t.realized_pnl > 0 THEN 1.0 ELSE 0.0 END) * 100, 1) AS win_rate_pct
FROM trades t
WHERE t.status = 'CLOSED' AND t.scan_ai_conviction IS NOT NULL
GROUP BY t.scan_ai_conviction
ORDER BY t.scan_ai_conviction;
```

### 2. Which gear setting performs best?
```sql
SELECT
    t.gear_at_entry                     AS gear,
    COUNT(*)                            AS trades,
    ROUND(AVG(t.realized_pnl_pct), 2)  AS avg_return_pct,
    ROUND(SUM(t.realized_pnl), 0)      AS total_pnl,
    ROUND(AVG(t.holding_days), 1)      AS avg_hold_days
FROM trades t
WHERE t.status = 'CLOSED'
GROUP BY t.gear_at_entry
ORDER BY avg_return_pct DESC;
```

### 3. Which exit reason is associated with the best/worst outcomes?
```sql
SELECT
    t.exit_reason,
    COUNT(*)                            AS trades,
    ROUND(AVG(t.realized_pnl_pct), 2)  AS avg_return_pct,
    ROUND(AVG(t.holding_days), 1)      AS avg_hold_days,
    ROUND(AVG(t.max_unrealized_pnl_pct), 2) AS avg_peak_pct
FROM trades t
WHERE t.status = 'CLOSED'
GROUP BY t.exit_reason;
```

### 4. How many stocks in each scan made it to each stage?
```sql
SELECT
    s.scan_id,
    s.started_at,
    s.gear_label,
    s.total_scanned,
    s.universe_filter_passed,
    s.technical_filter_passed,
    s.fundamental_filter_passed,
    s.sector_filter_passed,
    s.final_selected
FROM scans s
ORDER BY s.started_at DESC;
```

### 5. Was the stop loss too tight? (Check if price recovered after stop hit)
```sql
-- For stop-loss exits: compare exit_price to max price seen in the following 10 days
-- (This requires price data outside the simulator; annotate manually or via a price lookup.)
SELECT
    t.trade_id,
    t.symbol,
    t.entry_price,
    t.initial_sl,
    t.exit_price,
    t.realized_pnl_pct,
    t.atr_at_entry,
    t.trail_multiplier,
    t.scan_rsi_trigger
FROM trades t
WHERE t.exit_reason = 'Trailing Stop Hit'
  AND t.realized_pnl < 0
ORDER BY t.realized_pnl_pct;
```

### 6. Which filter stage wrongly rejected good stocks?
```sql
-- Find stocks in scans that were rejected at each stage, then check if the stock
-- went on to perform well (requires manual annotation or price lookup).
SELECT
    sc.scan_id,
    sc.symbol,
    sc.sector,
    sc.passed_universe_filter,
    sc.universe_fail_reason,
    sc.passed_technical_filter,
    sc.technical_fail_reason,
    sc.passed_fundamental_filter,
    sc.fundamental_fail_reason,
    sc.passed_sector_filter,
    sc.sector_fail_reason
FROM scan_candidates sc
WHERE sc.reached_final_shortlist = FALSE
ORDER BY sc.scan_id, sc.symbol;
```

### 7. How correlated are composite score and actual return?
```sql
SELECT
    ROUND(t.scan_composite_score / 10) * 10    AS score_bucket,
    COUNT(*)                                    AS trades,
    ROUND(AVG(t.realized_pnl_pct), 2)          AS avg_return_pct
FROM trades t
WHERE t.status = 'CLOSED' AND t.scan_composite_score IS NOT NULL
GROUP BY score_bucket
ORDER BY score_bucket;
```

### 8. Equity curve (net equity over time)
```sql
SELECT
    snapshot_time,
    net_equity,
    total_realized_pnl,
    unrealized_pnl,
    winning_trades,
    losing_trades
FROM account_snapshots
WHERE event_type IN ('trade_close', 'daily_close')
ORDER BY snapshot_time;
```

---

## Implementation Notes

### File location
```
backend/data/cognicap.db
```
Add to `.gitignore` alongside other state files in `backend/data/state/`.

### Python integration
Use Python's built-in `sqlite3` module or `SQLAlchemy` (already a transitive dep via LangGraph):

```python
# backend/services/db.py
import sqlite3
from pathlib import Path
from config import DB_PATH  # add DB_PATH = DATA_DIR / "cognicap.db" to config.py

def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row   # dict-like access
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")  # better concurrent read perf
    return conn
```

### Migration strategy
- Schema version tracked via SQLite `PRAGMA user_version`
- Add a `backend/migrations/` folder with numbered SQL files: `001_initial.sql`, `002_add_column.sql`, etc.
- Apply migrations on app startup in `create_app()` before registering blueprints

### Populating the DB

| Event | Where to write | Table |
|-------|---------------|-------|
| Scan started | `decision_support/stream.py` before pipeline | `scans` (status=running) |
| Each stage completes | `decision_support/tools.py` after each tool | `scan_candidates` (upsert) |
| Scan completed | `decision_support/stream.py` after all stages | `scans` (update counts, status=completed) |
| Stock analyzed on-demand | `stock_analyzer.py` / agent callback | `stock_analyses` |
| Trade entry confirmed | `simulator_engine.py` after `execute_trade` | `trades`, `account_snapshots` |
| Position tick | `simulator_engine.py` monitoring loop (every N ticks) | `position_snapshots` |
| Trade exit | `simulator_engine.py` in `close_position` | `trades` (update), `account_snapshots` |

### Position snapshot frequency
Record every 60 seconds (not every 5 seconds) to keep the table manageable.
The existing 5-second loop can update in-memory state; write to DB every 60s.

### Linking trades back to scans
When a user selects a stock from the shortlist and clicks "Buy", the frontend should
pass `scan_id` and `symbol` so the trade row can reference the scan that discovered it.
This is the critical join for outcome analysis.

---

## Schema Version History

| Version | Date | Changes |
|---------|------|---------|
| 1.0 | 2026-02-24 | Initial schema: scans, scan_candidates, stock_analyses, trades, position_snapshots, account_snapshots |
