"""Async order fill tracker for live Kite trading.

Polls Kite order history every 2s to confirm fills.
On COMPLETE: updates DB + places SL-M order.
On REJECTED: marks trade as failed.
"""

import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable, Dict, Optional

logger = logging.getLogger(__name__)

POLL_INTERVAL = 2    # seconds between status checks
MAX_RETRIES = 60     # 2 minutes total wait before giving up


class OrderTracker:
    """Background fill tracker for live Kite orders."""

    def __init__(self):
        self._executor = ThreadPoolExecutor(
            max_workers=4, thread_name_prefix="order-tracker"
        )

    def track_entry_order(
        self,
        broker,
        order_id: str,
        trade_record: Dict[str, Any],
        on_fill: Callable,
    ) -> None:
        """Start background tracking for an entry order.

        on_fill(trade_id, avg_price, filled_qty, sl_order_id, error_status=None)
        """
        self._executor.submit(
            self._poll_entry, broker, order_id, trade_record, on_fill
        )

    def track_exit_order(
        self,
        broker,
        order_id: str,
        trade_id: str,
        on_exit: Callable,
    ) -> None:
        """Start background tracking for an exit order.

        on_exit(trade_id, avg_price, filled_qty, error_status=None)
        """
        self._executor.submit(self._poll_exit, broker, order_id, trade_id, on_exit)

    def _poll_entry(self, broker, order_id: str, trade_record: Dict, on_fill: Callable) -> None:
        trade_id = trade_record.get("trade_id")
        symbol = trade_record.get("symbol")
        logger.info(f"[OrderTracker] Tracking entry {order_id} for {symbol} ({trade_id})")

        for _ in range(MAX_RETRIES):
            time.sleep(POLL_INTERVAL)
            try:
                history = broker.get_order_history(order_id)
                if not history:
                    continue
                latest = history[-1]
                status = latest.get("status", "")

                if status == "COMPLETE":
                    avg_price = latest.get("average_price", 0)
                    filled_qty = latest.get("filled_quantity", 0)

                    # Try to get precise avg_price from trades if not in history
                    if avg_price == 0:
                        try:
                            trades = broker.get_order_trades(order_id)
                            if trades:
                                total_value = sum(t["quantity"] * t["average_price"] for t in trades)
                                total_qty = sum(t["quantity"] for t in trades)
                                avg_price = total_value / total_qty if total_qty else 0
                                filled_qty = total_qty
                        except Exception:
                            pass

                    # Place SL-M order at initial trailing stop
                    sl_order_id = None
                    try:
                        atr = float(trade_record.get("atr_at_entry", 0))
                        multiplier = float(trade_record.get("trail_multiplier", 1.5))
                        trigger_price = round(avg_price - (multiplier * atr), 2)
                        if trigger_price > 0 and filled_qty > 0:
                            sl_order_id = broker.place_order(
                                variety=broker.VARIETY_REGULAR,
                                exchange=broker.EXCHANGE_NSE,
                                tradingsymbol=symbol,
                                transaction_type=broker.TRANSACTION_TYPE_SELL,
                                quantity=filled_qty,
                                order_type=broker.ORDER_TYPE_SLM,
                                product=broker.PRODUCT_CNC,
                                trigger_price=trigger_price,
                                tag=(trade_id or "")[:20],
                            )
                            logger.info(
                                f"[OrderTracker] SL-M placed for {symbol}: "
                                f"trigger={trigger_price}, sl_order_id={sl_order_id}"
                            )
                    except Exception as e:
                        logger.error(f"[OrderTracker] SL-M placement failed for {symbol}: {e}")

                    on_fill(trade_id, avg_price, filled_qty, sl_order_id)
                    return

                elif status in ("REJECTED", "CANCELLED"):
                    logger.warning(f"[OrderTracker] Entry {order_id} for {symbol}: {status}")
                    on_fill(trade_id, 0, 0, None, status)
                    return

            except Exception as e:
                logger.warning(f"[OrderTracker] Poll error for {order_id}: {e}")

        logger.error(
            f"[OrderTracker] Timeout on entry order {order_id} ({symbol}) after "
            f"{MAX_RETRIES * POLL_INTERVAL}s"
        )
        on_fill(trade_id, 0, 0, None, "TIMEOUT")

    def _poll_exit(self, broker, order_id: str, trade_id: str, on_exit: Callable) -> None:
        logger.info(f"[OrderTracker] Tracking exit {order_id} for trade {trade_id}")

        for _ in range(MAX_RETRIES):
            time.sleep(POLL_INTERVAL)
            try:
                history = broker.get_order_history(order_id)
                if not history:
                    continue
                latest = history[-1]
                status = latest.get("status", "")

                if status == "COMPLETE":
                    avg_price = latest.get("average_price", 0)
                    filled_qty = latest.get("filled_quantity", 0)
                    on_exit(trade_id, avg_price, filled_qty)
                    return

                elif status in ("REJECTED", "CANCELLED"):
                    logger.warning(f"[OrderTracker] Exit {order_id} for {trade_id}: {status}")
                    on_exit(trade_id, 0, 0, status)
                    return

            except Exception as e:
                logger.warning(f"[OrderTracker] Poll error for exit {order_id}: {e}")

        logger.error(f"[OrderTracker] Timeout on exit order {order_id} for {trade_id}")
        on_exit(trade_id, 0, 0, "TIMEOUT")

    def recover_pending_orders(self, broker) -> None:
        """On server restart, resume tracking any PENDING trades from DB."""
        try:
            from services.db import get_pending_entry_trades
            pending = get_pending_entry_trades()
            if not pending:
                return
            logger.info(f"[OrderTracker] Recovering {len(pending)} pending entry orders")
            for trade in pending:
                order_id = trade.get("entry_order_id")
                if order_id:
                    self.track_entry_order(
                        broker,
                        order_id,
                        trade,
                        self._make_db_fill_callback(trade["trade_id"]),
                    )
        except Exception as e:
            logger.error(f"[OrderTracker] Recovery failed: {e}")

    def _make_db_fill_callback(self, trade_id: str) -> Callable:
        """Fill callback that only updates the DB (used during recovery)."""
        def callback(tid, avg_price, filled_qty, sl_order_id=None, error_status=None):
            try:
                from services.db import update_trade_fill
                status = error_status if error_status else "FILLED"
                update_trade_fill(tid, avg_price or 0, filled_qty or 0, status, sl_order_id)
            except Exception as e:
                logger.error(f"[OrderTracker] Recovery DB callback failed for {trade_id}: {e}")
        return callback


# Module-level singleton
_tracker: Optional[OrderTracker] = None
_tracker_lock = threading.Lock()


def get_order_tracker() -> OrderTracker:
    """Get the global OrderTracker singleton."""
    global _tracker
    with _tracker_lock:
        if _tracker is None:
            _tracker = OrderTracker()
    return _tracker
