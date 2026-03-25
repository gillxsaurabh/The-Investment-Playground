"""Abstract TradingEngine interface.

Both PaperTradingSimulator and LiveTradingEngine implement this interface,
allowing all consumers (routes, automation, monitor) to work against it
without caring about the underlying execution mode.
"""

import logging
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from constants import (
    DEFAULT_TRAIL_MULTIPLIER,
    SPREAD_FACTOR,
    STALL_EXIT_DAYS,
    TRAIL_TIGHTEN_PROFIT_ATR,
    TRAIL_TIGHTEN_FACTOR,
)

logger = logging.getLogger(__name__)


class TradingEngine(ABC):
    """Abstract interface for all trading engines (simulator and live)."""

    @abstractmethod
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
        """Execute a buy order. Returns dict with success/failure details."""
        ...

    @abstractmethod
    def close_position(
        self,
        trade_id: str,
        exit_price: Optional[float] = None,
        reason: str = "Manual Close",
    ) -> Dict[str, Any]:
        """Close an open position. Returns dict with success/failure details."""
        ...

    @abstractmethod
    def get_positions_with_pnl(self) -> Dict[str, Any]:
        """Get all open positions enriched with live LTP and unrealized P&L."""
        ...

    @abstractmethod
    def get_account_summary(self) -> Dict[str, Any]:
        """Get current account summary (balance, P&L, etc.)."""
        ...

    @abstractmethod
    def monitor_positions(self, ltps: Optional[Dict[str, float]] = None) -> List[Dict[str, Any]]:
        """Check trailing stops and auto-close triggered positions."""
        ...

    @abstractmethod
    def get_price_history(self, minutes: int = 60) -> List[Dict[str, Any]]:
        """Return price history snapshots for the last N minutes."""
        ...

    @abstractmethod
    def record_price_snapshot(self, ltps: Optional[Dict[str, float]] = None) -> None:
        """Record a price snapshot for all open positions."""
        ...

    @abstractmethod
    def reset(self, initial_capital: float = 100_000.0) -> Dict[str, Any]:
        """Reset the engine to starting state (not applicable in live mode)."""
        ...

    @property
    @abstractmethod
    def mode(self) -> str:
        """Return 'simulator' or 'live'."""
        ...

    # --- Shared concrete implementation ---

    def update_exit_levels(
        self,
        position: Dict[str, Any],
        ltp: float,
    ) -> Tuple[Dict[str, Any], Optional[Dict[str, Any]]]:
        """Update trailing stop for a position based on current price.

        Engine-agnostic — called by both simulator and live engines.
        Returns (updated_position, exit_signal or None).
        """
        today = datetime.now().date()

        # Update high-water mark
        if ltp > position.get("highest_price_seen", position["entry_price"]):
            position["highest_price_seen"] = ltp
            position["last_new_high_date"] = today.strftime("%Y-%m-%d")

        # Ratchet trailing stop UP (never down)
        atr = position.get("atr_at_entry", 0)
        multiplier = position.get("trail_multiplier", DEFAULT_TRAIL_MULTIPLIER)
        if atr > 0:
            entry = float(position.get("entry_price", ltp))
            unrealized_profit = ltp - entry
            if (
                unrealized_profit >= TRAIL_TIGHTEN_PROFIT_ATR * atr
                and not position.get("trail_tightened")
            ):
                multiplier = round(multiplier * TRAIL_TIGHTEN_FACTOR, 4)
                position["trail_multiplier"] = multiplier
                position["trail_tightened"] = True
                logger.info(
                    f"[Engine] {position['symbol']} profit ≥ {TRAIL_TIGHTEN_PROFIT_ATR}×ATR — "
                    f"trail tightened to {multiplier:.2f}×ATR"
                )

            new_sl = round(position["highest_price_seen"] - (multiplier * atr), 2)
            current_sl = position.get("current_sl", position.get("stop_loss", 0))
            if new_sl > current_sl:
                position["current_sl"] = new_sl
                position["stop_loss"] = new_sl

        # Stall exit — count trading days without a new high
        last_high_str = position.get("last_new_high_date")
        if last_high_str:
            try:
                from automation.nse_holidays import count_trading_days
                last_high_date = datetime.strptime(last_high_str, "%Y-%m-%d").date()
                trading_days_stalled = count_trading_days(last_high_date, today)
                if trading_days_stalled >= STALL_EXIT_DAYS:
                    exit_price = round(ltp * (1 - SPREAD_FACTOR), 2)
                    return position, {
                        "should_exit": True,
                        "reason": f"Stall Exit - No new high in {trading_days_stalled} trading days",
                        "exit_price": exit_price,
                    }
            except (ValueError, ImportError):
                pass

        # Hard exit — trailing stop hit
        current_sl = position.get("current_sl", position.get("stop_loss", 0))
        if ltp <= current_sl:
            exit_price = round(ltp * (1 - SPREAD_FACTOR), 2)
            return position, {
                "should_exit": True,
                "reason": "Trailing Stop Hit",
                "exit_price": exit_price,
            }

        return position, None
