"""Pre-trade risk checks for live trading mode.

All live orders pass through RiskManager.pre_trade_check() before execution.
"""

import logging
from datetime import datetime, date, time as dtime
from typing import Tuple

import pytz

from constants import (
    LIVE_MAX_POSITION_SIZE,
    LIVE_MAX_DAILY_LOSS,
    LIVE_MAX_OPEN_POSITIONS,
    LIVE_MAX_ORDER_VALUE,
)

logger = logging.getLogger(__name__)

IST = pytz.timezone("Asia/Kolkata")
MARKET_OPEN = dtime(9, 15)
MARKET_CLOSE = dtime(15, 30)


class RiskManager:
    """Validates live orders before execution."""

    def pre_trade_check(
        self,
        symbol: str,
        quantity: int,
        ltp: float,
        available_equity: float,
        open_positions_count: int,
    ) -> Tuple[bool, str]:
        """Check if a trade is safe to execute.

        Returns (allowed, reason). reason is empty string if allowed.
        """
        order_value = ltp * quantity
        now_ist = datetime.now(IST)

        # 1. NSE holiday / weekend check
        try:
            from automation.nse_holidays import is_trading_day
            if not is_trading_day(now_ist.date()):
                return False, f"Today ({now_ist.date()}) is not a trading day (holiday/weekend)"
        except Exception:
            pass  # nse_holidays unavailable — let Kite reject the order itself

        # 2. Market hours check (NSE: 9:15 AM – 3:30 PM IST)
        now_time = now_ist.time()
        if not (MARKET_OPEN <= now_time <= MARKET_CLOSE):
            return False, f"Outside market hours ({now_time.strftime('%H:%M')} IST)"

        # 3. Max order value safety cap
        if order_value > LIVE_MAX_ORDER_VALUE:
            return False, (
                f"Order value ₹{order_value:,.0f} exceeds max ₹{LIVE_MAX_ORDER_VALUE:,.0f}"
            )

        # 4. Max position size as % of equity
        if available_equity > 0 and (order_value / available_equity) > LIVE_MAX_POSITION_SIZE:
            pct = (order_value / available_equity) * 100
            return False, (
                f"Position {pct:.1f}% of equity exceeds max {LIVE_MAX_POSITION_SIZE * 100:.0f}%"
            )

        # 5. Max open positions
        if open_positions_count >= LIVE_MAX_OPEN_POSITIONS:
            return False, f"Already at max {LIVE_MAX_OPEN_POSITIONS} open positions"

        return True, ""

    def check_daily_loss(
        self,
        realized_pnl_today: float,
        equity: float,
    ) -> Tuple[bool, str]:
        """Check if daily loss limit has been breached.

        Returns (breached, reason). reason is empty string if not breached.
        """
        if equity <= 0:
            return False, ""
        loss_pct = abs(min(realized_pnl_today, 0)) / equity
        if loss_pct >= LIVE_MAX_DAILY_LOSS:
            return True, (
                f"Daily loss {loss_pct:.1%} ≥ {LIVE_MAX_DAILY_LOSS:.0%} limit — "
                f"halting live trading for today"
            )
        return False, ""

    def check_daily_loss_from_db(self, equity: float) -> Tuple[bool, str]:
        """Query today's realized P&L from DB and check the daily loss limit.

        Returns (breached, reason). Fails open (returns False) on DB errors so
        a DB outage doesn't silently block all trading.
        """
        if equity <= 0:
            return False, ""
        try:
            from services.db import get_conn
            today = date.today().isoformat()
            conn = get_conn()
            row = conn.execute(
                "SELECT COALESCE(SUM(realized_pnl), 0) AS total "
                "FROM trades WHERE status='CLOSED' AND trading_mode='live' "
                "AND exit_time >= ?",
                (today + " 00:00:00",),
            ).fetchone()
            conn.close()
            today_pnl = row["total"] if row else 0
            return self.check_daily_loss(today_pnl, equity)
        except Exception as e:
            logger.warning(f"[RiskManager] daily_loss DB query failed (failing open): {e}")
            return False, ""
