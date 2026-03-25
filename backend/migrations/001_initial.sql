-- CogniCap SQLite schema v1.0
PRAGMA user_version = 1;

CREATE TABLE IF NOT EXISTS scans (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    scan_id         TEXT    NOT NULL UNIQUE,
    started_at      DATETIME NOT NULL,
    completed_at    DATETIME,
    status          TEXT    NOT NULL DEFAULT 'running',
    error_message   TEXT,
    gear            INTEGER NOT NULL,
    gear_label      TEXT    NOT NULL,
    universe        TEXT    NOT NULL,
    min_turnover    REAL    NOT NULL,
    rsi_buy_limit   INTEGER NOT NULL,
    adx_min         INTEGER NOT NULL,
    trail_multiplier REAL   NOT NULL,
    fundamental_check TEXT  NOT NULL,
    sector_5d_tolerance REAL NOT NULL,
    min_volume_ratio REAL   NOT NULL,
    vix             REAL,
    market_regime   TEXT,
    total_scanned                INTEGER,
    universe_filter_passed       INTEGER,
    technical_filter_passed      INTEGER,
    fundamental_filter_passed    INTEGER,
    sector_filter_passed         INTEGER,
    final_selected               INTEGER
);
CREATE INDEX IF NOT EXISTS idx_scans_started_at ON scans(started_at);
CREATE INDEX IF NOT EXISTS idx_scans_gear ON scans(gear);

CREATE TABLE IF NOT EXISTS scan_candidates (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    scan_id         TEXT    NOT NULL REFERENCES scans(scan_id) ON DELETE CASCADE,
    symbol          TEXT    NOT NULL,
    instrument_token INTEGER,
    sector          TEXT,
    sector_index    TEXT,
    current_price           REAL,
    avg_volume_20d          REAL,
    avg_turnover_20d        REAL,
    volume_ratio            REAL,
    ema_200                 REAL,
    stock_3m_return         REAL,
    nifty_3m_return         REAL,
    sector_3m_return        REAL,
    passed_universe_filter  BOOLEAN,
    universe_fail_reason    TEXT,
    ema_20                  REAL,
    rsi                     REAL,
    adx                     REAL,
    rsi_trigger             TEXT,
    passed_technical_filter BOOLEAN,
    technical_fail_reason   TEXT,
    profit_yoy_growing      BOOLEAN,
    profit_qoq_growing      BOOLEAN,
    quarterly_profit_growth BOOLEAN,
    roe                     REAL,
    debt_to_equity          REAL,
    passed_fundamental_filter BOOLEAN,
    fundamental_fail_reason   TEXT,
    sector_5d_change        REAL,
    passed_sector_filter    BOOLEAN,
    sector_fail_reason      TEXT,
    composite_score         REAL,
    score_technical         REAL,
    score_fundamental       REAL,
    score_relative_strength REAL,
    score_volume_health     REAL,
    ai_conviction           INTEGER,
    why_selected            TEXT,
    news_sentiment          INTEGER,
    news_flag               TEXT,
    news_headlines          TEXT,
    final_rank              INTEGER,
    final_rank_score        REAL,
    rank_reason             TEXT,
    rank_factor_conviction_norm   REAL,
    rank_factor_composite_norm    REAL,
    rank_factor_rs_norm           REAL,
    rank_factor_fundamental_norm  REAL,
    rank_factor_sector_norm       REAL,
    reached_final_shortlist BOOLEAN DEFAULT FALSE,
    UNIQUE (scan_id, symbol)
);
CREATE INDEX IF NOT EXISTS idx_scan_candidates_scan_id ON scan_candidates(scan_id);
CREATE INDEX IF NOT EXISTS idx_scan_candidates_symbol ON scan_candidates(symbol);
CREATE INDEX IF NOT EXISTS idx_scan_candidates_shortlist ON scan_candidates(scan_id, reached_final_shortlist);

CREATE TABLE IF NOT EXISTS stock_analyses (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol          TEXT    NOT NULL,
    analyzed_at     DATETIME NOT NULL,
    triggered_by    TEXT,
    overall_score   REAL,
    recency_score           REAL,
    recency_stock_return    REAL,
    recency_nifty_return    REAL,
    recency_outperformance  REAL,
    recency_detail          TEXT,
    trend_score             REAL,
    trend_adx               REAL,
    trend_ema_20            REAL,
    trend_ema_50            REAL,
    trend_strength          TEXT,
    trend_direction         TEXT,
    stats_explanation       TEXT,
    fundamental_score       REAL,
    fund_roe                REAL,
    fund_debt_to_equity     REAL,
    fund_sales_growth       REAL,
    fundamental_summary     TEXT,
    fundamental_explanation TEXT,
    news_score              REAL,
    news_explanation        TEXT
);
CREATE INDEX IF NOT EXISTS idx_stock_analyses_symbol ON stock_analyses(symbol);
CREATE INDEX IF NOT EXISTS idx_stock_analyses_analyzed_at ON stock_analyses(analyzed_at);

CREATE TABLE IF NOT EXISTS trades (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    trade_id        TEXT    NOT NULL UNIQUE,
    scan_id         TEXT REFERENCES scans(scan_id),
    scan_rank       INTEGER,
    scan_ai_conviction INTEGER,
    scan_composite_score REAL,
    scan_final_rank_score REAL,
    scan_rsi        REAL,
    scan_adx        REAL,
    scan_rsi_trigger TEXT,
    scan_news_flag  TEXT,
    symbol          TEXT    NOT NULL,
    instrument_token INTEGER,
    sector          TEXT,
    entry_ltp       REAL    NOT NULL,
    entry_price     REAL    NOT NULL,
    quantity        INTEGER NOT NULL,
    total_cost      REAL    NOT NULL,
    entry_time      DATETIME NOT NULL,
    atr_at_entry    REAL    NOT NULL,
    trail_multiplier REAL   NOT NULL,
    initial_sl      REAL    NOT NULL,
    risk_per_share  REAL    NOT NULL,
    risk_per_trade  REAL    NOT NULL,
    highest_price_seen REAL,
    last_new_high_date DATE,
    current_sl      REAL,
    entry_order_id  TEXT,
    sl_order_id     TEXT,
    entry_status    TEXT DEFAULT 'FILLED',
    exit_ltp        REAL,
    exit_price      REAL,
    exit_time       DATETIME,
    exit_reason     TEXT,
    realized_pnl    REAL,
    realized_pnl_pct REAL,
    max_unrealized_pnl REAL,
    max_unrealized_pnl_pct REAL,
    holding_days    INTEGER,
    status          TEXT    NOT NULL DEFAULT 'OPEN',
    gear_at_entry   INTEGER,
    automation_run_id TEXT,
    account_balance_before REAL,
    account_balance_after  REAL,
    trading_mode    TEXT DEFAULT 'simulator'
);
CREATE INDEX IF NOT EXISTS idx_trades_symbol ON trades(symbol);
CREATE INDEX IF NOT EXISTS idx_trades_scan_id ON trades(scan_id);
CREATE INDEX IF NOT EXISTS idx_trades_status ON trades(status);
CREATE INDEX IF NOT EXISTS idx_trades_entry_time ON trades(entry_time);
CREATE INDEX IF NOT EXISTS idx_trades_exit_reason ON trades(exit_reason);
CREATE INDEX IF NOT EXISTS idx_trades_entry_status ON trades(entry_status);

CREATE TABLE IF NOT EXISTS position_snapshots (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    trade_id        TEXT    NOT NULL REFERENCES trades(trade_id) ON DELETE CASCADE,
    symbol          TEXT    NOT NULL,
    snapshot_time   DATETIME NOT NULL,
    ltp             REAL    NOT NULL,
    entry_price     REAL    NOT NULL,
    current_sl      REAL    NOT NULL,
    highest_price_seen REAL NOT NULL,
    unrealized_pnl  REAL    NOT NULL,
    unrealized_pnl_pct REAL NOT NULL,
    quantity        INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_position_snapshots_trade_id ON position_snapshots(trade_id);
CREATE INDEX IF NOT EXISTS idx_position_snapshots_time ON position_snapshots(trade_id, snapshot_time);

CREATE TABLE IF NOT EXISTS account_snapshots (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    snapshot_time   DATETIME NOT NULL,
    event_type      TEXT    NOT NULL,
    trade_id        TEXT,
    initial_capital REAL    NOT NULL,
    current_balance REAL    NOT NULL,
    total_realized_pnl REAL NOT NULL,
    open_position_cost REAL NOT NULL,
    unrealized_pnl  REAL    NOT NULL,
    net_equity      REAL    NOT NULL,
    total_trades    INTEGER NOT NULL,
    winning_trades  INTEGER NOT NULL,
    losing_trades   INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_account_snapshots_time ON account_snapshots(snapshot_time);
CREATE INDEX IF NOT EXISTS idx_account_snapshots_event ON account_snapshots(event_type);
