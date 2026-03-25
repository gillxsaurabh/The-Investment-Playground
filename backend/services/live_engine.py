"""Live trading engine — places real CNC orders via Kite Connect.

Uses SQLite (services/db.py) for position state instead of JSON files.
Applies pre-trade risk checks (services/risk_manager.py) before every order.
Tracks fills asynchronously via services/order_tracker.py.
"""

import logging
import threading
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from broker.base import BrokerAdapter
from constants import DEFAULT_TRAIL_MULTIPLIER, SPREAD_FACTOR, MAX_HISTORY_SECONDS
from services.trading_engine import TradingEngine
from services.risk_manager import RiskManager
from services.order_tracker import get_order_tracker

logger = logging.getLogger(__name__)


class LiveTradingEngine(TradingEngine):
    """Real Kite order execution engine backed by SQLite position state."""

    def __init__(self, broker: BrokerAdapter):
        self.broker = broker
        self._lock = threading.Lock()
        self._history_lock = threading.Lock()
        self._positions: Dict[str, Dict[str, Any]] = {}   # trade_id -> position dict
        self._price_history: List[Dict[str, Any]] = []
        self._risk = RiskManager()
        self._tracker = get_order_tracker()
        self._load_positions_from_db()

    @property
    def mode(self) -> str:
        return "live"

    # ---------------------------------------------------------------------------
    # Init helpers
    # ---------------------------------------------------------------------------

    def _load_positions_from_db(self) -> None:
        """Load open live trades from SQLite into memory on startup."""
        try:
            from services.db import get_open_trades
            rows = get_open_trades(trading_mode="live")
            with self._lock:
                for row in rows:
                    if row.get("entry_status") in ("FILLED", "PARTIAL"):
                        self._positions[row["trade_id"]] = dict(row)
            logger.info(f"[LiveEngine] Loaded {len(self._positions)} open live positions from DB")
        except Exception as e:
            logger.error(f"[LiveEngine] Failed to load positions from DB: {e}")

    # ---------------------------------------------------------------------------
    # TradingEngine interface
    # ---------------------------------------------------------------------------

    def execute_order(
        self,
        symbol: str,
        quantity: int,
        atr_at_entry: float,
        trail_multiplier: float = DEFAULT_TRAIL_MULTIPLIER,
        instrument_token: Optional[int] = None,
        ltp: Optional[float] = None,
        automation_run_id: Optional[str] = None,
        automation_gear: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Place a real CNC market buy order via Kite Connect."""
        try:
            # Fetch live LTP if not provided
            if ltp is None:
                ltp_data = self.broker.get_ltp([f"NSE:{symbol}"])
                ltp = ltp_data.get(f"NSE:{symbol}", {}).get("last_price", 0)

            if not ltp or ltp <= 0:
                return {"success": False, "error": f"Could not fetch LTP for {symbol}"}

            # Get available equity for risk check
            try:
                margins = self.broker.get_margins("equity")
                available_equity = margins.get("net", 0) or margins.get("available", {}).get("live_balance", 0)
            except Exception:
                available_equity = 0

            with self._lock:
                open_count = len(self._positions)

            # Pre-trade risk check
            allowed, reason = self._risk.pre_trade_check(
                symbol, quantity, ltp, available_equity, open_count
            )
            if not allowed:
                return {"success": False, "error": f"Risk check failed: {reason}"}

            # Place market buy order
            order_id = self.broker.place_order(
                variety=self.broker.VARIETY_REGULAR,
                exchange=self.broker.EXCHANGE_NSE,
                tradingsymbol=symbol,
                transaction_type=self.broker.TRANSACTION_TYPE_BUY,
                quantity=quantity,
                order_type=self.broker.ORDER_TYPE_MARKET,
                product=self.broker.PRODUCT_CNC,
                tag=(automation_run_id or "LIVE")[:20],
            )

            now = datetime.now()
            trade_id = f"LIVE_{now.strftime('%d%m%y')}_{symbol}_{order_id[-6:]}"
            initial_sl = round(ltp - (trail_multiplier * atr_at_entry), 2)

            position = {
                "trade_id": trade_id,
                "symbol": symbol,
                "instrument_token": instrument_token,
                "entry_ltp": ltp,
                "entry_price": ltp,   # will be updated on fill
                "quantity": quantity,
                "atr_at_entry": round(atr_at_entry, 2),
                "trail_multiplier": trail_multiplier,
                "initial_sl": initial_sl,
                "current_sl": initial_sl,
                "stop_loss": initial_sl,
                "highest_price_seen": ltp,
                "last_new_high_date": now.strftime("%Y-%m-%d"),
                "entry_time": now.strftime("%Y-%m-%d %H:%M:%S"),
                "entry_order_id": order_id,
                "sl_order_id": None,
                "entry_status": "PENDING",
                "status": "OPEN",
                "automation_run_id": automation_run_id,
                "automation_gear": automation_gear,
                "trading_mode": "live",
            }

            # Persist to DB
            try:
                from services.db import insert_trade
                insert_trade(position)
            except Exception as e:
                logger.warning(f"[LiveEngine] DB insert failed for {trade_id}: {e}")

            # Add to memory (PENDING state — will be updated on fill)
            with self._lock:
                self._positions[trade_id] = position

            # Start async fill tracking
            self._tracker.track_entry_order(
                self.broker, order_id, position,
                self._on_entry_fill,
            )

            logger.info(f"[LiveEngine] Buy order placed: {symbol} x{quantity} @ market, order_id={order_id}")
            return {
                "success": True,
                "trade_id": trade_id,
                "symbol": symbol,
                "order_id": order_id,
                "quantity": quantity,
                "entry_status": "PENDING",
                "message": f"LIVE BUY order placed: {quantity} x {symbol} — tracking fill...",
            }

        except Exception as e:
            logger.error(f"[LiveEngine] execute_order failed for {symbol}: {e}", exc_info=True)
            return {"success": False, "error": str(e)}

    def close_position(
        self,
        trade_id: str,
        exit_price: Optional[float] = None,
        reason: str = "Manual Close",
    ) -> Dict[str, Any]:
        """Cancel SL-M and place a real CNC market sell order."""
        with self._lock:
            position = self._positions.get(trade_id)

        if position is None:
            return {"success": False, "error": f"Position {trade_id} not found"}

        symbol = position["symbol"]
        qty = int(position.get("quantity", 0))
        sl_order_id = position.get("sl_order_id")

        try:
            # Cancel existing SL-M if present
            if sl_order_id:
                try:
                    self.broker.cancel_order(
                        variety=self.broker.VARIETY_REGULAR,
                        order_id=sl_order_id,
                    )
                    logger.info(f"[LiveEngine] Cancelled SL-M {sl_order_id} for {symbol}")
                except Exception as e:
                    logger.warning(f"[LiveEngine] Could not cancel SL-M {sl_order_id}: {e}")

            # Place market sell
            exit_order_id = self.broker.place_order(
                variety=self.broker.VARIETY_REGULAR,
                exchange=self.broker.EXCHANGE_NSE,
                tradingsymbol=symbol,
                transaction_type=self.broker.TRANSACTION_TYPE_SELL,
                quantity=qty,
                order_type=self.broker.ORDER_TYPE_MARKET,
                product=self.broker.PRODUCT_CNC,
                tag=trade_id[:20],
            )

            # Store exit reason for the fill callback
            with self._lock:
                if trade_id in self._positions:
                    self._positions[trade_id]["_exit_reason"] = reason

            # Start async exit tracking
            self._tracker.track_exit_order(
                self.broker, exit_order_id, trade_id,
                self._on_exit_fill,
            )

            logger.info(f"[LiveEngine] Sell order placed: {symbol} x{qty}, order_id={exit_order_id}")
            return {
                "success": True,
                "trade_id": trade_id,
                "symbol": symbol,
                "exit_order_id": exit_order_id,
                "entry_status": "EXIT_PENDING",
                "message": f"LIVE SELL order placed: {symbol} x{qty} — tracking fill...",
            }

        except Exception as e:
            logger.error(f"[LiveEngine] close_position failed for {trade_id}: {e}", exc_info=True)
            return {"success": False, "error": str(e)}

    def get_positions_with_pnl(self) -> Dict[str, Any]:
        """Read open live positions from memory, enrich with live LTPs."""
        with self._lock:
            positions = [p for p in self._positions.values()
                         if p.get("entry_status") in ("FILLED", "PARTIAL")]

        if not positions:
            return {
                "account_summary": self.get_account_summary(),
                "positions": [],
                "trade_history": self._get_closed_trades(),
            }

        symbols = list({p["symbol"] for p in positions})
        try:
            ltp_keys = [f"NSE:{s}" for s in symbols]
            ltp_data = self.broker.get_ltp(ltp_keys)
            ltps = {s: ltp_data.get(f"NSE:{s}", {}).get("last_price", 0) for s in symbols}
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

        summary = self.get_account_summary()
        summary["unrealized_pnl"] = round(total_unrealized, 2)

        return {
            "account_summary": summary,
            "positions": enriched,
            "trade_history": self._get_closed_trades(),
        }

    def get_account_summary(self) -> Dict[str, Any]:
        """Get real account balance from Kite + aggregate realized P&L from DB."""
        try:
            margins = self.broker.get_margins("equity")
            net = margins.get("net", 0)
            available = margins.get("available", {}).get("live_balance", net)
        except Exception:
            net = 0
            available = 0

        # Aggregate realized P&L from DB
        total_pnl = 0.0
        try:
            from services.db import get_conn
            conn = get_conn()
            row = conn.execute(
                "SELECT SUM(realized_pnl) as total FROM trades WHERE status='CLOSED' AND trading_mode='live'"
            ).fetchone()
            conn.close()
            total_pnl = round(row["total"] or 0, 2)
        except Exception:
            pass

        return {
            "mode": "live",
            "current_balance": round(available, 2),
            "net_equity": round(net, 2),
            "total_pnl": total_pnl,
        }

    def monitor_positions(self, ltps: Optional[Dict[str, float]] = None) -> List[Dict[str, Any]]:
        """Update trailing stops and handle exits. Modifies Kite SL-M orders as SL ratchets."""
        with self._lock:
            positions = [p for p in self._positions.values()
                         if p.get("entry_status") in ("FILLED", "PARTIAL")]
            if not positions:
                return []

        if ltps is None:
            symbols = list({p["symbol"] for p in positions})
            try:
                ltp_keys = [f"NSE:{s}" for s in symbols]
                ltp_data = self.broker.get_ltp(ltp_keys)
                ltps = {s: ltp_data.get(f"NSE:{s}", {}).get("last_price") for s in symbols}
            except Exception:
                return []

        closed = []
        for pos in list(positions):
            trade_id = pos["trade_id"]
            ltp = ltps.get(pos["symbol"])
            if ltp is None:
                continue

            old_sl = pos.get("current_sl", 0)
            updated_pos, exit_signal = self.update_exit_levels(pos, ltp)

            # Update memory
            with self._lock:
                if trade_id in self._positions:
                    self._positions[trade_id] = updated_pos

            new_sl = updated_pos.get("current_sl", old_sl)

            # SL ratcheted up — modify the Kite SL-M order
            if new_sl > old_sl and updated_pos.get("sl_order_id"):
                try:
                    self.broker.modify_order(
                        variety=self.broker.VARIETY_REGULAR,
                        order_id=updated_pos["sl_order_id"],
                        trigger_price=new_sl,
                    )
                    logger.info(
                        f"[LiveEngine] SL-M modified for {pos['symbol']}: "
                        f"{old_sl} → {new_sl}"
                    )
                    # Persist SL update to DB
                    try:
                        from services.db import update_trade_sl
                        update_trade_sl(
                            trade_id, new_sl, updated_pos.get("highest_price_seen", ltp),
                            updated_pos.get("sl_order_id"),
                        )
                    except Exception:
                        pass
                except Exception as e:
                    logger.warning(f"[LiveEngine] SL-M modify failed for {pos['symbol']}: {e}")

            # Stall exit — close the position
            if exit_signal and exit_signal["should_exit"]:
                result = self.close_position(
                    trade_id,
                    reason=exit_signal["reason"],
                )
                if result.get("success"):
                    closed.append(result)

        return closed

    def get_price_history(self, minutes: int = 60) -> List[Dict[str, Any]]:
        with self._history_lock:
            cutoff = (datetime.now() - timedelta(minutes=minutes)).strftime("%Y-%m-%d %H:%M:%S")
            return [s for s in self._price_history if s["time"] >= cutoff]

    def record_price_snapshot(self, ltps: Optional[Dict[str, float]] = None) -> None:
        """Record price snapshot for all open live positions."""
        with self._lock:
            positions = [p for p in self._positions.values()
                         if p.get("entry_status") in ("FILLED", "PARTIAL")]
            if not positions:
                return

        if ltps is None:
            symbols = list({p["symbol"] for p in positions})
            try:
                ltp_keys = [f"NSE:{s}" for s in symbols]
                ltp_data = self.broker.get_ltp(ltp_keys)
                ltps = {s: ltp_data.get(f"NSE:{s}", {}).get("last_price", 0) for s in symbols}
            except Exception:
                return

        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        values = {}
        for p in positions:
            ltp_val = ltps.get(p["symbol"])
            if ltp_val and p["entry_price"]:
                ltp_f = float(ltp_val)
                entry_f = float(p["entry_price"])
                qty_i = int(p["quantity"])
                values[p["symbol"]] = {
                    "pct": round(((ltp_f - entry_f) / entry_f) * 100, 4),
                    "ltp": ltp_f,
                    "entry_price": entry_f,
                    "stop_loss": float(p.get("current_sl", 0)),
                    "highest_price_seen": float(p.get("highest_price_seen", entry_f)),
                    "unrealized_pnl": round((ltp_f - entry_f) * qty_i, 2),
                    "quantity": qty_i,
                }

        with self._history_lock:
            self._price_history.append({"time": now, "values": values})
            # Prune old entries
            cutoff = (datetime.now() - timedelta(seconds=MAX_HISTORY_SECONDS)).strftime(
                "%Y-%m-%d %H:%M:%S"
            )
            self._price_history = [s for s in self._price_history if s["time"] >= cutoff]

    def reset(self, initial_capital: float = 100_000.0) -> Dict[str, Any]:
        return {"success": False, "error": "reset() is not applicable in live trading mode"}

    # ---------------------------------------------------------------------------
    # Fill callbacks (called by OrderTracker on background thread)
    # ---------------------------------------------------------------------------

    def _on_entry_fill(
        self,
        trade_id: str,
        avg_price: float,
        filled_qty: int,
        sl_order_id: Optional[str],
        error_status: Optional[str] = None,
    ) -> None:
        """Called when an entry order is confirmed or rejected."""
        if error_status:
            logger.warning(f"[LiveEngine] Entry fill failed for {trade_id}: {error_status}")
            try:
                from services.db import update_trade_fill
                update_trade_fill(trade_id, 0, 0, error_status)
            except Exception:
                pass
            with self._lock:
                self._positions.pop(trade_id, None)
            return

        # Update position with actual fill price
        with self._lock:
            if trade_id in self._positions:
                pos = self._positions[trade_id]
                pos["entry_price"] = avg_price
                pos["quantity"] = filled_qty
                pos["entry_status"] = "FILLED"
                pos["sl_order_id"] = sl_order_id
                # Recalculate SL based on actual fill price
                atr = pos.get("atr_at_entry", 0)
                multiplier = pos.get("trail_multiplier", DEFAULT_TRAIL_MULTIPLIER)
                pos["current_sl"] = round(avg_price - (multiplier * atr), 2)
                pos["stop_loss"] = pos["current_sl"]

        # Persist to DB
        try:
            from services.db import update_trade_fill
            update_trade_fill(trade_id, avg_price, filled_qty, "FILLED", sl_order_id)
        except Exception as e:
            logger.warning(f"[LiveEngine] DB fill update failed for {trade_id}: {e}")

        logger.info(
            f"[LiveEngine] Entry fill confirmed: {trade_id} @ {avg_price}, "
            f"qty={filled_qty}, sl_order={sl_order_id}"
        )

    def _on_exit_fill(
        self,
        trade_id: str,
        avg_price: float,
        filled_qty: int,
        error_status: Optional[str] = None,
    ) -> None:
        """Called when an exit order is confirmed or rejected."""
        if error_status:
            logger.warning(f"[LiveEngine] Exit fill failed for {trade_id}: {error_status}")
            return

        with self._lock:
            pos = self._positions.pop(trade_id, None)

        if not pos:
            return

        entry_price = float(pos.get("entry_price", avg_price))
        qty = int(pos.get("quantity", filled_qty))
        realized_pnl = round((avg_price - entry_price) * qty, 2)
        pnl_pct = round(
            (avg_price - entry_price) / entry_price * 100, 2
        ) if entry_price else 0
        exit_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        try:
            entry_dt = datetime.strptime(pos["entry_time"], "%Y-%m-%d %H:%M:%S")
            holding_days = (datetime.now() - entry_dt).days
        except Exception:
            holding_days = 0

        exit_reason = pos.get("_exit_reason", "Manual Close")

        try:
            from services.db import update_trade_exit
            update_trade_exit(trade_id, avg_price, exit_time, exit_reason,
                              realized_pnl, pnl_pct, holding_days)
        except Exception as e:
            logger.warning(f"[LiveEngine] DB exit update failed for {trade_id}: {e}")

        logger.info(
            f"[LiveEngine] Exit fill confirmed: {trade_id} @ {avg_price}, "
            f"P&L={realized_pnl} ({pnl_pct:.2f}%)"
        )

    # ---------------------------------------------------------------------------
    # Helpers
    # ---------------------------------------------------------------------------

    def _get_closed_trades(self) -> List[Dict[str, Any]]:
        """Return recent closed trades from DB."""
        try:
            from services.db import get_conn
            conn = get_conn()
            rows = conn.execute(
                "SELECT * FROM trades WHERE status='CLOSED' AND trading_mode='live' "
                "ORDER BY exit_time DESC LIMIT 50"
            ).fetchall()
            conn.close()
            return [dict(row) for row in rows]
        except Exception:
            return []

    def reconcile_positions(self) -> Dict[str, Any]:
        """Sync internal state with Kite holdings (live mode only).

        - Holdings in Kite but not in DB → flag as 'untracked'
        - Trades in DB but not in Kite → mark as 'External Close'
        """
        try:
            holdings = self.broker.get_holdings()
            kite_symbols = {h["tradingsymbol"] for h in holdings if h.get("quantity", 0) > 0}

            from services.db import get_open_trades, update_trade_exit
            open_trades = get_open_trades(trading_mode="live")
            db_symbols = {t["symbol"] for t in open_trades}

            untracked = kite_symbols - db_symbols
            externally_closed = db_symbols - kite_symbols

            # Mark externally closed trades
            for trade in open_trades:
                if trade["symbol"] in externally_closed:
                    exit_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    update_trade_exit(
                        trade["trade_id"], 0, exit_time, "External Close", 0, 0, 0
                    )
                    with self._lock:
                        self._positions.pop(trade["trade_id"], None)
                    logger.warning(
                        f"[LiveEngine] Reconcile: {trade['symbol']} closed externally"
                    )

            result = {
                "success": True,
                "untracked_holdings": list(untracked),
                "externally_closed": list(externally_closed),
            }
            if untracked:
                logger.warning(
                    f"[LiveEngine] Reconcile: untracked Kite holdings: {untracked}"
                )
            return result

        except Exception as e:
            logger.error(f"[LiveEngine] Reconcile failed: {e}", exc_info=True)
            return {"success": False, "error": str(e)}
