"""Weekly automation orchestrator for the 4-2-1-1 stock selection and trading pipeline.

Runs every Monday at 9:00 AM IST:
1. Checks how many previous Monday's automation positions are still open.
2. Determines how many new stocks to buy (target 6 total active automation positions).
3. Runs the pipeline for Gear 5 (Turbo), Gear 3 (Balanced), Gear 4 (Growth).
4. Picks top 2 from each gear, deduplicates across gears.
5. Falls back to Gear 2 (Bricks/Cautious) and Gear 1 (Fortress) if shortfall.
6. Executes trades via paper simulator (or live Kite, depending on mode).
7. Saves run record to automation_state.json.
"""

import json
import logging
from datetime import datetime, date
from pathlib import Path

import pytz

from config import TOKEN_FILE, SIMULATOR_DATA_FILE, AUTOMATION_STATE_FILE
from services.file_lock import locked_json_read, atomic_json_write
from constants import (
    VIX_HIGH_THRESHOLD, VIX_RSI_TIGHTENING,
    VIX_TIER1_THRESHOLD, VIX_TIER2_THRESHOLD, VIX_TIER3_THRESHOLD,
    VIX_TIER1_RSI_TIGHTEN, VIX_TIER2_RSI_TIGHTEN,
    RISK_PER_TRADE_PCT, MAX_POSITION_PCT,
    AUTO_SELL_URGENCY_THRESHOLD,
    MAX_DRAWDOWN_PCT,
)
from agents.decision_support.strategy_config import STRATEGY_GEARS
from agents.decision_support.tools import (
    filter_market_universe,
    analyze_technicals,
    check_fundamentals,
    check_sector_health,
    compute_composite_scores,
    ai_rank_stocks,
    rank_final_shortlist,
)
from agents.shared.data_infra import PipelineSession
from automation.nse_holidays import is_trading_day
from broker import get_broker

logger = logging.getLogger(__name__)

IST = pytz.timezone("Asia/Kolkata")
TARGET_POSITIONS = 6
PICKS_PER_GEAR = 2
PRIMARY_GEARS = [5, 3, 4]      # Turbo, Balanced, Growth
FALLBACK_GEARS = [2, 1]        # Bricks/Cautious, Fortress
MAX_FALLBACK_DEPTH = 10        # How deep into a gear's ranked list to look for dedup


# ---------------------------------------------------------------------------
# State helpers
# ---------------------------------------------------------------------------

def _load_state() -> dict:
    return locked_json_read(
        AUTOMATION_STATE_FILE,
        default={"enabled": False, "mode": "simulator", "last_run": None, "history": []},
    )


def _save_state(state: dict) -> None:
    atomic_json_write(AUTOMATION_STATE_FILE, state, indent=2, default=str)


def _load_access_token() -> str | None:
    data = locked_json_read(TOKEN_FILE, default=None)
    if data is None:
        return None
    return data.get("access_token")


# ---------------------------------------------------------------------------
# Position helpers
# ---------------------------------------------------------------------------

def _count_open_automation_positions(_run_id: str = None) -> int:
    """Count ALL open positions that were opened by automation (any run)."""
    state = _load_state()
    mode = state.get("mode", "simulator")

    if mode == "live":
        # Count from SQLite for live mode
        try:
            from services.db import get_conn
            conn = get_conn()
            row = conn.execute(
                "SELECT COUNT(*) as cnt FROM trades WHERE status='OPEN' "
                "AND trading_mode='live' AND automation_run_id IS NOT NULL"
            ).fetchone()
            conn.close()
            return row["cnt"] if row else 0
        except Exception as e:
            logger.warning(f"[Automation] Could not count live positions from DB: {e}")
            return 0

    # Simulator mode: read from JSON
    try:
        data = locked_json_read(SIMULATOR_DATA_FILE, default={})
        open_positions = data.get("active_positions", [])
        return sum(1 for p in open_positions if p.get("automation_run_id"))
    except Exception as e:
        logger.warning(f"[Automation] Could not read simulator data: {e}")
        return 0


# ---------------------------------------------------------------------------
# Sell pipeline runner
# ---------------------------------------------------------------------------

def _run_sell_audit(access_token: str) -> list[dict]:
    """Run the sell pipeline and auto-close positions scoring STRONG SELL.

    Returns list of closed trade results.
    """
    from agents.decision_support.sell_tools import (
        fetch_portfolio_holdings,
        enrich_holdings_with_technicals,
        enrich_holdings_with_fundamentals,
        enrich_holdings_with_sector,
        compute_sell_scores,
        ai_rank_sell_candidates,
    )
    from agents.shared.data_infra import PipelineSession

    def log_fn(msg: str):
        logger.info(f"[Automation][SellAudit] {msg}")

    try:
        sell_session = PipelineSession()

        # Fetch VIX for market regime
        broker = get_broker(access_token)
        kite = broker.raw_kite
        market_regime = {"vix": None, "regime": "normal"}
        try:
            vix_quote = kite.quote(["NSE:INDIA VIX"])
            vix_value = vix_quote.get("NSE:INDIA VIX", {}).get("last_price", 0)
            market_regime["vix"] = round(vix_value, 2) if vix_value else None
            if vix_value >= VIX_TIER2_THRESHOLD:
                market_regime["regime"] = "high_fear"
            elif vix_value >= VIX_TIER1_THRESHOLD:
                market_regime["regime"] = "fearful"
            else:
                market_regime["regime"] = "normal"
        except Exception:
            pass

        holdings = fetch_portfolio_holdings(access_token, log=log_fn, session=sell_session)
        if not holdings:
            log_fn("No holdings found — skipping sell audit")
            return []

        holdings = enrich_holdings_with_technicals(holdings, kite, log=log_fn, session=sell_session)
        holdings = enrich_holdings_with_fundamentals(holdings, log=log_fn, session=sell_session)
        holdings = enrich_holdings_with_sector(holdings, access_token, log=log_fn, session=sell_session)
        holdings = compute_sell_scores(holdings, log=log_fn, session=sell_session)
        holdings = ai_rank_sell_candidates(holdings, market_regime, log=log_fn, session=sell_session)

        # Auto-close positions flagged as STRONG SELL
        strong_sell = [
            h for h in holdings
            if h.get("sell_urgency_score", 0) >= AUTO_SELL_URGENCY_THRESHOLD
        ]

        if not strong_sell:
            log_fn("No STRONG SELL positions found — nothing to auto-close")
            return []

        # Use the active engine (simulator or live) to close positions
        from services.engine_factory import get_trading_engine
        engine = get_trading_engine(access_token)
        closed = []
        for holding in strong_sell:
            symbol = holding["symbol"]
            positions = engine.get_positions_with_pnl().get("positions", [])
            for pos in positions:
                if pos["symbol"] == symbol:
                    result = engine.close_position(
                        pos["trade_id"],
                        reason=f"Sell Audit — urgency {holding['sell_urgency_score']}/100 ({holding['sell_urgency_label']})",
                    )
                    if result.get("success"):
                        log_fn(
                            f"Auto-closed {symbol} — urgency {holding['sell_urgency_score']}/100: "
                            f"{holding.get('sell_reason', '')}"
                        )
                        closed.append(result)
                    break

        log_fn(f"Sell audit complete: {len(strong_sell)} STRONG SELL detected, {len(closed)} positions closed")
        return closed

    except Exception as e:
        logger.error(f"[Automation][SellAudit] Sell pipeline failed: {e}", exc_info=True)
        return []


# ---------------------------------------------------------------------------
# Pipeline runner for a single gear
# ---------------------------------------------------------------------------

def _run_pipeline_for_gear(access_token: str, gear_number: int) -> list[dict]:
    """Run the full 6-stage pipeline for a given gear and return ranked stock list."""
    config = STRATEGY_GEARS.get(gear_number)
    if not config:
        logger.error(f"[Automation] Unknown gear: {gear_number}")
        return []

    label = config.get("label", f"Gear{gear_number}")
    logger.info(f"[Automation] Starting pipeline for {label} (Gear {gear_number})")

    # Create a fresh request-scoped cache so gears don't bleed into each other
    session = PipelineSession()

    def log_fn(msg: str):
        logger.info(f"[Automation][{label}] {msg}")

    rsi_buy_limit = config["rsi_buy_limit"]
    vix_value = None

    # Market regime detection
    try:
        broker = get_broker(access_token)
        kite = broker.raw_kite
        vix_quote = kite.quote(["NSE:INDIA VIX"])
        vix_value = vix_quote.get("NSE:INDIA VIX", {}).get("last_price", 0)
        if vix_value >= VIX_TIER3_THRESHOLD:
            logger.warning(
                f"[Automation][{label}] Extreme VIX ({vix_value:.1f} ≥ {VIX_TIER3_THRESHOLD}) — skipping gear"
            )
            return []
        elif vix_value >= VIX_TIER2_THRESHOLD:
            rsi_buy_limit = max(20, rsi_buy_limit - VIX_TIER2_RSI_TIGHTEN)
            logger.info(
                f"[Automation][{label}] High fear VIX ({vix_value:.1f}), tightened RSI by "
                f"{VIX_TIER2_RSI_TIGHTEN} → {rsi_buy_limit}"
            )
        elif vix_value >= VIX_TIER1_THRESHOLD:
            rsi_buy_limit = max(20, rsi_buy_limit - VIX_TIER1_RSI_TIGHTEN)
            logger.info(
                f"[Automation][{label}] Elevated VIX ({vix_value:.1f}), tightened RSI by "
                f"{VIX_TIER1_RSI_TIGHTEN} → {rsi_buy_limit}"
            )
    except Exception as e:
        logger.warning(f"[Automation][{label}] VIX fetch failed: {e}")

    if vix_value and vix_value >= VIX_TIER2_THRESHOLD:
        regime = "high_fear"
    elif vix_value and vix_value >= VIX_TIER1_THRESHOLD:
        regime = "fearful"
    else:
        regime = "normal"
    market_regime = {
        "vix": round(vix_value, 2) if vix_value else None,
        "regime": regime,
    }

    try:
        # Stage 1: Market Scanner
        stocks = filter_market_universe(
            access_token,
            log=log_fn,
            min_turnover=config["min_turnover"],
            universe=config["universe"],
            session=session,
        )
        if not stocks:
            logger.info(f"[Automation][{label}] Stage 1 returned 0 stocks — skipping gear")
            return []

        # Stage 2: Technicals
        stocks = analyze_technicals(stocks, log=log_fn, rsi_buy_limit=rsi_buy_limit, session=session)
        if not stocks:
            logger.info(f"[Automation][{label}] Stage 2 returned 0 stocks — skipping gear")
            return []

        # Stage 3: Fundamentals
        stocks = check_fundamentals(stocks, log=log_fn, fundamental_check=config["fundamental_check"], session=session)
        if not stocks:
            logger.info(f"[Automation][{label}] Stage 3 returned 0 stocks — skipping gear")
            return []

        # Stage 4: Sector Health
        stocks = check_sector_health(access_token, stocks, log=log_fn, session=session)
        if not stocks:
            logger.info(f"[Automation][{label}] Stage 4 returned 0 stocks — skipping gear")
            return []

        # Stage 5: Composite Scores + AI Conviction
        stocks = compute_composite_scores(stocks, log=log_fn, session=session)
        stocks = ai_rank_stocks(stocks, market_regime, log=log_fn, session=session)

        # Stage 6: Portfolio Ranker
        stocks = rank_final_shortlist(stocks, log=log_fn, session=session)

        logger.info(f"[Automation][{label}] Pipeline complete — {len(stocks)} stocks ranked")
        return stocks

    except Exception as e:
        logger.error(f"[Automation][{label}] Pipeline failed: {e}", exc_info=True)
        return []


# ---------------------------------------------------------------------------
# Deduplication
# ---------------------------------------------------------------------------

def _pick_top_n_deduplicated(
    gear_results: list[tuple[int, list[dict]]],
    n_per_gear: int,
    seen_symbols: set,
) -> list[dict]:
    """Pick top N stocks per gear, skipping any already in seen_symbols.

    Args:
        gear_results: List of (gear_number, ranked_stocks) tuples.
        n_per_gear: How many to pick from each gear.
        seen_symbols: Set of symbols already selected (modified in place).

    Returns:
        List of selected stock dicts (with 'automation_gear' field added).
    """
    selected = []
    for gear_number, stocks in gear_results:
        picks_from_gear = 0
        label = STRATEGY_GEARS.get(gear_number, {}).get("label", f"Gear{gear_number}")
        for stock in stocks[:MAX_FALLBACK_DEPTH]:
            if picks_from_gear >= n_per_gear:
                break
            symbol = stock.get("symbol")
            if not symbol or symbol in seen_symbols:
                if symbol in seen_symbols:
                    logger.info(f"[Automation] {symbol} already picked — skipping for {label}")
                continue
            seen_symbols.add(symbol)
            selected.append({**stock, "automation_gear": gear_number})
            picks_from_gear += 1
            logger.info(f"[Automation] Selected {symbol} from {label} (rank #{stock.get('final_rank', '?')})")
    return selected


# ---------------------------------------------------------------------------
# Trade execution
# ---------------------------------------------------------------------------

def _execute_trades(
    access_token: str,
    picks: list[dict],
    automation_run_id: str,
    stocks_to_buy: int,
    mode: str = "simulator",
) -> list[dict]:
    """Execute trades for selected stocks via the active TradingEngine.

    Works for both simulator and live mode — the engine handles
    the mode-specific execution (virtual vs real Kite order).
    """
    import pandas as pd
    from datetime import timedelta
    from broker import get_broker
    from services.engine_factory import get_trading_engine

    results = []
    engine = get_trading_engine(access_token, mode)
    broker = get_broker(access_token)
    kite = broker.raw_kite

    account = engine.get_account_summary()
    # Simulator has initial_capital/current_balance; live has net_equity/current_balance
    available_balance = account.get("current_balance", 0)
    total_capital = account.get("initial_capital", account.get("net_equity", available_balance))

    logger.info(
        f"[Automation][{mode.upper()}] Available balance: ₹{available_balance:.2f}, "
        f"total capital: ₹{total_capital:.2f}"
    )

    for stock in picks:
        symbol = stock.get("symbol")
        instrument_token = stock.get("instrument_token")
        gear = stock.get("automation_gear")
        atr_multiplier = STRATEGY_GEARS.get(gear, {}).get("atr_stop_loss_multiplier", 1.5)

        try:
            # Fetch live LTP
            ltp_key = f"NSE:{symbol}"
            quote = kite.quote([ltp_key])
            ltp = quote[ltp_key]["last_price"]

            # Calculate ATR from 45 days of daily candles
            today = date.today()
            from_date = (today - timedelta(days=45)).strftime("%Y-%m-%d")
            to_date = today.strftime("%Y-%m-%d")
            candles = kite.historical_data(instrument_token, from_date, to_date, "day")
            if len(candles) >= 14:
                from services.technical import calculate_atr
                candle_df = pd.DataFrame(candles).rename(columns={
                    "open": "Open", "high": "High",
                    "low": "Low", "close": "Close", "volume": "Volume",
                })
                atr = calculate_atr(candle_df, period=14)
            else:
                atr = ltp * 0.02  # fallback: 2% of price

            # Risk-based position sizing: risk 1% of total capital per trade
            risk_amount = total_capital * RISK_PER_TRADE_PCT
            risk_per_share = atr_multiplier * atr
            if risk_per_share > 0:
                quantity = max(1, int(risk_amount / risk_per_share))
            else:
                quantity = max(1, int(available_balance / (stocks_to_buy * ltp * 1.0005)))

            # Cap at MAX_POSITION_PCT of total capital
            max_quantity = max(1, int((total_capital * MAX_POSITION_PCT) / ltp))
            quantity = min(quantity, max_quantity)

            logger.info(
                f"[Automation][{mode.upper()}] {symbol}: ATR={atr:.2f}, "
                f"risk/share={risk_per_share:.2f}, qty={quantity}"
            )

            result = engine.execute_order(
                symbol=symbol,
                quantity=quantity,
                atr_at_entry=atr,
                trail_multiplier=atr_multiplier,
                instrument_token=instrument_token,
                ltp=ltp,
                automation_run_id=automation_run_id,
                automation_gear=gear,
            )
            results.append({"symbol": symbol, "gear": gear, **result})
            status = "OK" if result.get("success") else f"FAILED: {result.get('error')}"
            logger.info(f"[Automation][{mode.upper()}] Trade {symbol}: {status}")

        except Exception as e:
            logger.error(
                f"[Automation][{mode.upper()}] Trade execution failed for {symbol}: {e}",
                exc_info=True,
            )
            results.append({"symbol": symbol, "gear": gear, "success": False, "error": str(e)})

    return results


# ---------------------------------------------------------------------------
# Main orchestrator
# ---------------------------------------------------------------------------

def run_weekly_automation(dry_run: bool = False) -> dict:
    """Main entry point for the weekly Monday automation.

    Args:
        dry_run: If True, run discovery but skip trade execution.

    Returns:
        Dict with run summary (stocks_selected, trades_executed, status, etc.)
    """
    now_ist = datetime.now(IST)
    today = now_ist.date()
    run_id = f"AUTO_{today.strftime('%Y%m%d')}"

    logger.info(f"[Automation] Starting weekly automation — run_id={run_id}, dry_run={dry_run}")

    # --- Holiday check ---
    if not is_trading_day(today):
        msg = f"Today ({today}) is a market holiday or weekend — skipping automation"
        logger.info(f"[Automation] {msg}")
        return {"status": "skipped", "reason": msg, "run_id": run_id}

    # --- Load state ---
    state = _load_state()
    if not state.get("enabled") and not dry_run:
        msg = "Automation is disabled — skipping"
        logger.info(f"[Automation] {msg}")
        return {"status": "skipped", "reason": msg, "run_id": run_id}

    mode = state.get("mode", "simulator")

    # --- Access token ---
    access_token = _load_access_token()
    if not access_token:
        msg = "No valid access token found — please log in to Zerodha first"
        logger.error(f"[Automation] {msg}")
        _record_failed_run(state, run_id, msg)
        return {"status": "error", "reason": msg, "run_id": run_id}

    # --- Step 1: Run sell audit — close STRONG SELL positions first ---
    sell_closures = []
    if not dry_run:
        logger.info(f"[Automation] Running sell audit before buying...")
        sell_closures = _run_sell_audit(access_token)
        if sell_closures:
            logger.info(f"[Automation] Sell audit closed {len(sell_closures)} positions")

    # --- Count ALL still-open automation positions (across all past runs) ---
    still_open = _count_open_automation_positions()
    stocks_to_buy = TARGET_POSITIONS - still_open

    last_run = state.get("last_run") or {}
    logger.info(f"[Automation] Last run: {last_run.get('run_id') or 'None'}, total open automation positions: {still_open}, to buy: {stocks_to_buy}")

    # --- Drawdown circuit breaker ---
    if not dry_run:
        try:
            from services.engine_factory import get_trading_engine
            engine_tmp = get_trading_engine(access_token, mode)
            acct = engine_tmp.get_account_summary()
            initial = acct.get("initial_capital", acct.get("net_equity", 0))
            current = acct.get("current_balance", 0)
            if initial > 0:
                drawdown = (initial - current) / initial
                if drawdown >= MAX_DRAWDOWN_PCT:
                    msg = (
                        f"Circuit breaker triggered: account down {drawdown:.1%} from initial capital "
                        f"(>{MAX_DRAWDOWN_PCT:.0%} threshold). Skipping new entries."
                    )
                    logger.warning(f"[Automation] {msg}")
                    run_record = {
                        "run_id": run_id, "date": str(today),
                        "started_at": now_ist.isoformat(),
                        "completed_at": datetime.now(IST).isoformat(),
                        "status": "skipped",
                        "reason": msg,
                        "stocks_selected": [],
                        "trades_executed": 0,
                        "trade_results": [],
                        "sell_closures": [
                            {"symbol": r.get("symbol"), "realized_pnl": r.get("realized_pnl"), "reason": r.get("reason")}
                            for r in sell_closures
                        ],
                    }
                    _update_state(state, run_record)
                    return run_record
        except Exception as e:
            logger.warning(f"[Automation] Drawdown check failed: {e}")

    if stocks_to_buy <= 0:
        msg = f"All {TARGET_POSITIONS} automation positions still running — nothing to buy"
        logger.info(f"[Automation] {msg}")
        run_record = {
            "run_id": run_id, "date": str(today),
            "started_at": now_ist.isoformat(),
            "completed_at": datetime.now(IST).isoformat(),
            "previous_positions_still_open": still_open,
            "stocks_to_buy": 0,
            "stocks_selected": [],
            "trades_executed": 0,
            "trade_results": [],
            "status": "skipped",
            "reason": msg,
        }
        _update_state(state, run_record)
        return run_record

    # --- Global VIX Tier 3 circuit breaker: pause all new entries in extreme fear ---
    try:
        broker_vix = get_broker(access_token)
        vix_global_quote = broker_vix.raw_kite.quote(["NSE:INDIA VIX"])
        vix_global = vix_global_quote.get("NSE:INDIA VIX", {}).get("last_price", 0)
        if vix_global and vix_global >= VIX_TIER3_THRESHOLD:
            msg = (
                f"VIX Tier 3 circuit breaker triggered: VIX={vix_global:.1f} ≥ {VIX_TIER3_THRESHOLD} "
                f"(extreme fear). Pausing all new entries this week."
            )
            logger.warning(f"[Automation] {msg}")
            run_record = {
                "run_id": run_id, "date": str(today),
                "started_at": now_ist.isoformat(),
                "completed_at": datetime.now(IST).isoformat(),
                "status": "skipped",
                "reason": msg,
                "vix": round(vix_global, 2),
                "previous_positions_still_open": still_open,
                "stocks_to_buy": stocks_to_buy,
                "stocks_selected": [],
                "trades_executed": 0,
                "trade_results": [],
                "sell_closures": [
                    {"symbol": r.get("symbol"), "realized_pnl": r.get("realized_pnl"), "reason": r.get("reason")}
                    for r in sell_closures
                ],
            }
            _update_state(state, run_record)
            return run_record
    except Exception as e:
        logger.warning(f"[Automation] Global VIX Tier 3 check failed: {e}")

    # --- Run pipelines for primary gears ---
    seen_symbols: set = set()
    gear_results = []
    for gear in PRIMARY_GEARS:
        label = STRATEGY_GEARS[gear]["label"]
        logger.info(f"[Automation] Running pipeline for {label} (Gear {gear})")
        ranked = _run_pipeline_for_gear(access_token, gear)
        gear_results.append((gear, ranked))
        logger.info(f"[Automation] {label} pipeline returned {len(ranked)} stocks")

    # Pick top PICKS_PER_GEAR from each primary gear (with dedup)
    final_picks = _pick_top_n_deduplicated(gear_results, PICKS_PER_GEAR, seen_symbols)
    logger.info(f"[Automation] After primary gears: {len(final_picks)}/{stocks_to_buy} stocks selected")

    # --- Fallback gears if shortfall ---
    if len(final_picks) < stocks_to_buy:
        for gear in FALLBACK_GEARS:
            if len(final_picks) >= stocks_to_buy:
                break
            needed = stocks_to_buy - len(final_picks)
            label = STRATEGY_GEARS[gear]["label"]
            logger.info(f"[Automation] Shortfall — running {label} (Gear {gear}) to fill {needed} slots")
            ranked = _run_pipeline_for_gear(access_token, gear)
            fallback_picks = _pick_top_n_deduplicated([(gear, ranked)], needed, seen_symbols)
            final_picks.extend(fallback_picks)
            logger.info(f"[Automation] {label} contributed {len(fallback_picks)} stocks")

    # Trim to exactly stocks_to_buy
    final_picks = final_picks[:stocks_to_buy]
    logger.info(f"[Automation] Final selection: {[s['symbol'] for s in final_picks]}")

    selected_summary = [
        {
            "symbol": s.get("symbol"),
            "gear": s.get("automation_gear"),
            "gear_label": STRATEGY_GEARS.get(s.get("automation_gear"), {}).get("label"),
            "final_rank": s.get("final_rank"),
            "composite_score": s.get("composite_score"),
            "ai_conviction": s.get("ai_conviction"),
        }
        for s in final_picks
    ]

    if dry_run:
        logger.info(f"[Automation] Dry run complete — no trades executed")
        return {
            "status": "dry_run",
            "run_id": run_id,
            "stocks_to_buy": stocks_to_buy,
            "stocks_selected": selected_summary,
            "trades_executed": 0,
            "trade_results": [],
        }

    # --- Execute trades ---
    logger.info(f"[Automation] Executing {len(final_picks)} trades in {mode} mode...")
    trade_results = _execute_trades(access_token, final_picks, run_id, stocks_to_buy, mode)

    successful = sum(1 for r in trade_results if r.get("success"))
    logger.info(f"[Automation] Trades complete: {successful}/{len(final_picks)} successful")

    run_record = {
        "run_id": run_id,
        "date": str(today),
        "started_at": now_ist.isoformat(),
        "completed_at": datetime.now(IST).isoformat(),
        "previous_positions_still_open": still_open,
        "stocks_to_buy": stocks_to_buy,
        "stocks_selected": selected_summary,
        "trades_executed": successful,
        "trade_results": [
            {"symbol": r.get("symbol"), "gear": r.get("gear"),
             "success": r.get("success"), "error": r.get("error"),
             "trade_id": r.get("trade_id"), "entry_price": r.get("entry_price"),
             "quantity": r.get("quantity")}
            for r in trade_results
        ],
        "mode": mode,
        "status": "completed",
        "error": None,
        "sell_closures": [
            {"symbol": r.get("symbol"), "realized_pnl": r.get("realized_pnl"), "reason": r.get("reason")}
            for r in sell_closures
        ],
    }

    _update_state(state, run_record)
    logger.info(f"[Automation] Run {run_id} complete. State saved.")
    return run_record


def _record_failed_run(state: dict, run_id: str, error_msg: str) -> None:
    now_ist = datetime.now(IST)
    run_record = {
        "run_id": run_id,
        "date": str(now_ist.date()),
        "started_at": now_ist.isoformat(),
        "completed_at": now_ist.isoformat(),
        "status": "error",
        "error": error_msg,
        "stocks_selected": [],
        "trades_executed": 0,
    }
    _update_state(state, run_record)


def _update_state(state: dict, run_record: dict) -> None:
    state["last_run"] = run_record
    history = state.get("history", [])
    history.insert(0, run_record)
    state["history"] = history[:10]  # Keep last 10 runs
    _save_state(state)
