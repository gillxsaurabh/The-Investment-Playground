"""NSE trading holidays for 2026.

Source: NSE India official holiday list.
Update this list each year by visiting https://www.nseindia.com/
"""

from datetime import date

NSE_HOLIDAYS_2026 = {
    "2026-01-26",  # Republic Day
    "2026-02-26",  # Mahashivratri
    "2026-03-19",  # Holi (2nd day)
    "2026-04-02",  # Ram Navami
    "2026-04-03",  # Good Friday
    "2026-04-14",  # Dr. Ambedkar Jayanti / Baisakhi
    "2026-05-01",  # Maharashtra Day / Labour Day
    "2026-06-16",  # Eid ul-Adha (Bakri Id) — subject to moon sighting
    "2026-08-15",  # Independence Day
    "2026-08-27",  # Ganesh Chaturthi
    "2026-10-02",  # Gandhi Jayanti / Dussehra
    "2026-10-20",  # Diwali Laxmi Pujan (Muhurat trading day — market may open briefly)
    "2026-10-21",  # Diwali Balipratipada
    "2026-11-04",  # Guru Nanak Jayanti
    "2026-11-25",  # Christmas (observed)
    "2026-12-25",  # Christmas Day
}


def is_market_holiday(check_date: date | None = None) -> bool:
    """Return True if the given date (or today) is an NSE trading holiday."""
    if check_date is None:
        check_date = date.today()
    return check_date.strftime("%Y-%m-%d") in NSE_HOLIDAYS_2026


def is_trading_day(check_date: date | None = None) -> bool:
    """Return True if the given date is a valid NSE trading day (Mon-Fri, not a holiday)."""
    if check_date is None:
        check_date = date.today()
    if check_date.weekday() >= 5:  # Saturday=5, Sunday=6
        return False
    return not is_market_holiday(check_date)


def count_trading_days(from_date: date, to_date: date) -> int:
    """Count NSE trading days between from_date (inclusive) and to_date (exclusive).

    Used for stall-exit logic so weekends and holidays don't count against
    a position that simply had no market session.
    """
    from datetime import timedelta
    count = 0
    current = from_date
    while current < to_date:
        if is_trading_day(current):
            count += 1
        current += timedelta(days=1)
    return count
