"""Paper Trading Simulator Engine.

Moved from backend/simulator.py to services/simulator_engine.py.
Uses config.py for file paths and constants.py for magic numbers.
"""

import json
import logging
import random
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path

from config import SIMULATOR_DATA_FILE, SIMULATOR_PRICE_HISTORY_FILE
from constants import (
    SPREAD_FACTOR,
    MAX_HISTORY_SECONDS,
    DEFAULT_TRAIL_MULTIPLIER,
    DEFAULT_INITIAL_CAPITAL,
)
from services.trading_engine import TradingEngine

logger = logging.getLogger(__name__)


class PaperTradingSimulator(TradingEngine):
    """Paper trading engine that executes virtual trades and tracks P&L using live Kite prices."""

    @property
    def mode(self) -> str:
        return "simulator"

    def __init__(self, kite, data_file=None, history_file=None):
        self.kite = kite
        self.data_file = str(data_file or SIMULATOR_DATA_FILE)
        self.history_file = str(history_file or SIMULATOR_PRICE_HISTORY_FILE)
        self._lock = threading.Lock()
        self._history_lock = threading.Lock()
        self._load_data()
        self._load_price_history()

    def _load_data(self):
        path = Path(self.data_file)
        if path.exists():
            with open(path, "r") as f:
                self._data = json.load(f)
            # Migrate old-format positions to trailing stop format
            migrated = False
            for i, p in enumerate(self._data["active_positions"]):
                if "current_sl" not in p:
                    self._data["active_positions"][i] = self._migrate_position_to_trailing(p)
                    migrated = True
            if migrated:
                self._save_data()
        else:
            self._data = {
                "account_summary": {
                    "initial_capital": DEFAULT_INITIAL_CAPITAL,
                    "current_balance": DEFAULT_INITIAL_CAPITAL,
                    "total_pnl": 0.0,
                },
                "active_positions": [],
                "trade_history": [],
            }
            path.parent.mkdir(parents=True, exist_ok=True)
            self._save_data()

    def _save_data(self):
        with open(self.data_file, "w") as f:
            json.dump(self._data, f, indent=2, default=str)

    def _load_price_history(self):
        """Load price history from file, pruning entries older than 1 hour."""
        path = Path(self.history_file)
        if path.exists():
            with open(path, "r") as f:
                self._price_history = json.load(f)
        else:
            self._price_history = []
        self._prune_history()

    def _save_price_history(self):
        Path(self.history_file).parent.mkdir(parents=True, exist_ok=True)
        with open(self.history_file, "w") as f:
            json.dump(self._price_history, f, default=str)

    def _prune_history(self):
        """Remove snapshots older than MAX_HISTORY_SECONDS."""
        cutoff = (datetime.now() - timedelta(seconds=MAX_HISTORY_SECONDS)).strftime(
            "%Y-%m-%d %H:%M:%S"
        )
        self._price_history = [s for s in self._price_history if s["time"] >= cutoff]

    def record_price_snapshot(self, ltps=None):
        """Record current normalized % values for all active positions.

        Args:
            ltps: Pre-fetched LTP map {symbol: price}. If None, fetches from Kite.
        """
        with self._lock:
            positions = self._data["active_positions"]
            if not positions:
                return

            if ltps is None:
                symbols = [p["symbol"] for p in positions]
                try:
                    ltps = self._fetch_ltps(symbols)
                except Exception:
                    return

        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        values = {}
        for p in positions:
            ltp = ltps.get(p["symbol"])
            if ltp and p["entry_price"]:
                ltp_f = float(ltp)
                entry_f = float(p["entry_price"])
                qty_i = int(p["quantity"])
                values[p["symbol"]] = {
                    "pct": round(((ltp_f - entry_f) / entry_f) * 100, 4),
                    "ltp": ltp_f,
                    "entry_price": entry_f,
                    "stop_loss": float(p.get("current_sl", p.get("stop_loss", 0))),
                    "highest_price_seen": float(p.get("highest_price_seen", entry_f)),
                    "unrealized_pnl": round((ltp_f - entry_f) * qty_i, 2),
                    "quantity": qty_i,
                }

        with self._history_lock:
            self._price_history.append({"time": now, "values": values})
            self._prune_history()

    def get_price_history(self, minutes=60):
        """Return price history for the last N minutes."""
        with self._history_lock:
            cutoff = (datetime.now() - timedelta(minutes=minutes)).strftime(
                "%Y-%m-%d %H:%M:%S"
            )
            return [s for s in self._price_history if s["time"] >= cutoff]

    def _fetch_ltp(self, symbol):
        """Fetch live LTP from Kite for a single symbol."""
        key = f"NSE:{symbol}"
        quote = self.kite.quote([key])
        return quote[key]["last_price"]

    def _fetch_ltps(self, symbols):
        """Batch fetch LTPs for multiple symbols."""
        if not symbols:
            return {}
        keys = [f"NSE:{s}" for s in symbols]
        quotes = self.kite.quote(keys)
        return {s: quotes[f"NSE:{s}"]["last_price"] for s in symbols}

    def execute_order(self, symbol, quantity, atr_at_entry, trail_multiplier=DEFAULT_TRAIL_MULTIPLIER,
                      instrument_token=None, ltp=None, automation_run_id=None, automation_gear=None):
        """Execute a virtual buy order with spread simulation and trailing stop.

        Args:
            ltp: If provided, use this price instead of fetching live from Kite.
                 Prevents race conditions where a price move between modal open
                 and confirm causes "Insufficient Virtual Funds".
            automation_run_id: Optional tag (e.g. "AUTO_20260223") for automation tracking.
            automation_gear: Optional gear number (1-5) this trade was selected from.
        """
        with self._lock:
            if ltp is None:
                ltp = self._fetch_ltp(symbol)
            entry_price = round(ltp * (1 + SPREAD_FACTOR), 2)
            total_cost = entry_price * quantity

            if self._data["account_summary"]["current_balance"] < total_cost:
                return {
                    "success": False,
                    "error": "Insufficient Virtual Funds",
                    "required": total_cost,
                    "available": self._data["account_summary"]["current_balance"],
                }

            now = datetime.now()
            trade_id = f"SIM_{now.strftime('%d%m%y')}_{symbol}_{random.randint(1000, 9999)}"
            initial_sl = round(entry_price - (trail_multiplier * atr_at_entry), 2)

            position = {
                "trade_id": trade_id,
                "symbol": symbol,
                "instrument_token": instrument_token,
                "entry_price": entry_price,
                "quantity": quantity,
                "atr_at_entry": round(atr_at_entry, 2),
                "current_sl": initial_sl,
                "highest_price_seen": entry_price,
                "last_new_high_date": now.strftime("%Y-%m-%d"),
                "trail_multiplier": trail_multiplier,
                "stop_loss": initial_sl,
                "entry_time": now.strftime("%Y-%m-%d %H:%M:%S"),
                "status": "OPEN",
                "automation_run_id": automation_run_id,
                "automation_gear": automation_gear,
            }

            self._data["account_summary"]["current_balance"] -= total_cost
            self._data["account_summary"]["current_balance"] = round(
                self._data["account_summary"]["current_balance"], 2
            )
            self._data["active_positions"].append(position)
            self._save_data()

            # Secondary persistence: write to SQLite (fire-and-forget)
            try:
                from services.db import insert_trade
                insert_trade({
                    **position,
                    "total_cost": total_cost,
                    "initial_sl": initial_sl,
                    "entry_status": "FILLED",
                    "trading_mode": "simulator",
                    "account_balance_before": self._data["account_summary"]["current_balance"] + total_cost,
                    "account_balance_after": self._data["account_summary"]["current_balance"],
                })
            except Exception:
                pass

            return {
                "success": True,
                "trade_id": trade_id,
                "symbol": symbol,
                "entry_price": entry_price,
                "quantity": quantity,
                "total_cost": total_cost,
                "current_sl": initial_sl,
                "trail_multiplier": trail_multiplier,
                "message": f"Virtual BUY executed: {quantity} x {symbol} @ {entry_price}",
            }

    def close_position(self, trade_id, exit_price=None, reason="Manual Close"):
        """Close a virtual position and move to history."""
        with self._lock:
            position = None
            idx = None
            for i, p in enumerate(self._data["active_positions"]):
                if p["trade_id"] == trade_id:
                    position = p
                    idx = i
                    break

            if position is None:
                return {"success": False, "error": f"Position {trade_id} not found"}

            if exit_price is None:
                ltp = self._fetch_ltp(position["symbol"])
                exit_price = round(ltp * (1 - SPREAD_FACTOR), 2)

            exit_price = float(exit_price)
            entry = float(position["entry_price"])
            qty = int(position["quantity"])
            credit = exit_price * qty
            realized_pnl = round((exit_price - entry) * qty, 2)

            self._data["account_summary"]["current_balance"] += credit
            self._data["account_summary"]["current_balance"] = round(
                self._data["account_summary"]["current_balance"], 2
            )
            self._data["account_summary"]["total_pnl"] += realized_pnl
            self._data["account_summary"]["total_pnl"] = round(
                self._data["account_summary"]["total_pnl"], 2
            )

            history_entry = {
                **position,
                "exit_price": exit_price,
                "exit_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "realized_pnl": realized_pnl,
                "reason": reason,
                "status": "CLOSED",
            }

            self._data["active_positions"].pop(idx)
            self._data["trade_history"].insert(0, history_entry)
            self._save_data()

            # Secondary persistence: update SQLite (fire-and-forget)
            try:
                from services.db import update_trade_exit
                entry_dt = datetime.strptime(str(position["entry_time"]), "%Y-%m-%d %H:%M:%S")
                holding_days = (datetime.now() - entry_dt).days
                pnl_pct = round((exit_price - entry) / entry * 100, 2) if entry else 0
                update_trade_exit(
                    trade_id, exit_price,
                    datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    reason, realized_pnl, pnl_pct, holding_days,
                )
            except Exception:
                pass

            return {
                "success": True,
                "trade_id": trade_id,
                "symbol": position["symbol"],
                "exit_price": exit_price,
                "realized_pnl": realized_pnl,
                "reason": reason,
                "message": f"Virtual SELL: {position['symbol']} @ {exit_price} | P&L: {realized_pnl}",
            }

    def get_positions_with_pnl(self):
        """Get all active positions enriched with live LTP and unrealized P&L."""
        with self._lock:
            positions = self._data["active_positions"]
            if not positions:
                return {
                    "account_summary": self._data["account_summary"],
                    "positions": [],
                    "trade_history": self._data["trade_history"],
                }

            symbols = [p["symbol"] for p in positions]
            try:
                ltps = self._fetch_ltps(symbols)
            except Exception:
                ltps = {}

            enriched = []
            total_unrealized = 0.0
            for p in positions:
                ltp = float(ltps.get(p["symbol"], p["entry_price"]))
                entry = float(p["entry_price"])
                qty = int(p["quantity"])
                unrealized_pnl = round((ltp - entry) * qty, 2)
                total_unrealized += unrealized_pnl
                enriched.append({**p, "ltp": ltp, "unrealized_pnl": unrealized_pnl})

            return {
                "account_summary": {
                    **self._data["account_summary"],
                    "unrealized_pnl": round(total_unrealized, 2),
                },
                "positions": enriched,
                "trade_history": self._data["trade_history"],
            }

    # update_exit_levels is inherited from TradingEngine base class

    def monitor_positions(self, ltps=None):
        """Background check: update trailing stops and auto-close when triggered.

        Args:
            ltps: Pre-fetched LTP map {symbol: price}. If None, fetches from Kite.
        """
        with self._lock:
            positions = self._data["active_positions"]
            if not positions:
                return []

            if ltps is None:
                symbols = [p["symbol"] for p in positions]
                try:
                    ltps = self._fetch_ltps(symbols)
                except Exception:
                    return []

        to_close = []
        for i, p in enumerate(positions):
            ltp = ltps.get(p["symbol"])
            if ltp is None:
                continue

            updated_pos, exit_signal = self.update_exit_levels(p, ltp)

            with self._lock:
                if i < len(self._data["active_positions"]):
                    self._data["active_positions"][i] = updated_pos

            if exit_signal and exit_signal["should_exit"]:
                to_close.append(
                    (p["trade_id"], exit_signal["exit_price"], exit_signal["reason"])
                )

        with self._lock:
            self._save_data()

        closed = []
        for trade_id, exit_price, reason in to_close:
            result = self.close_position(trade_id, exit_price, reason)
            if result.get("success"):
                closed.append(result)
                logger.info(f"Auto-closed: {result['message']}")

        return closed

    def _migrate_position_to_trailing(self, position):
        """Migrate old-format position to trailing stop format."""
        entry_price = position["entry_price"]
        old_sl = position.get("stop_loss", entry_price * 0.95)

        estimated_atr = (
            round((entry_price - old_sl) / DEFAULT_TRAIL_MULTIPLIER, 2)
            if entry_price > old_sl
            else round(entry_price * 0.03, 2)
        )

        position["atr_at_entry"] = estimated_atr
        position["current_sl"] = old_sl
        position["highest_price_seen"] = entry_price
        position["last_new_high_date"] = position["entry_time"].split(" ")[0]
        position["trail_multiplier"] = DEFAULT_TRAIL_MULTIPLIER
        position["stop_loss"] = old_sl
        return position

    def reset(self, initial_capital=DEFAULT_INITIAL_CAPITAL):
        """Reset simulator to starting state."""
        with self._lock:
            self._data = {
                "account_summary": {
                    "initial_capital": initial_capital,
                    "current_balance": initial_capital,
                    "total_pnl": 0.0,
                },
                "active_positions": [],
                "trade_history": [],
            }
            self._save_data()
        with self._history_lock:
            self._price_history = []
            self._save_price_history()
        return {"success": True, "message": f"Simulator reset with capital: {initial_capital}"}

    def get_account_summary(self):
        """Get current account summary."""
        with self._lock:
            return {**self._data["account_summary"]}


def start_position_monitor(engine, interval=1):
    """Start a daemon thread that monitors positions for any TradingEngine.

    - Records a price snapshot every tick (1s) for smooth charting.
    - Checks SL/trailing stops every 5 ticks to manage exits.
    - For PaperTradingSimulator: also persists price history to disk every 5 ticks.
    """

    def _monitor_loop():
        tick = 0
        while True:
            time.sleep(interval)
            try:
                engine.record_price_snapshot()
                tick += 1
                if tick % 5 == 0:
                    engine.monitor_positions()
                    # Simulator-specific: flush price history to disk
                    if hasattr(engine, "_history_lock") and hasattr(engine, "_save_price_history"):
                        with engine._history_lock:
                            engine._save_price_history()
            except Exception as e:
                logger.warning(f"Position monitor error: {e}")
                tick += 1

    t = threading.Thread(target=_monitor_loop, daemon=True)
    t.start()
    logger.info(
        f"Position monitor started for {engine.mode} engine "
        f"(snapshot: {interval}s, SL check: {interval * 5}s)"
    )
