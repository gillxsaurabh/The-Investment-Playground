"""Screener.in fundamental data scraping.

Consolidates the duplicated scraping logic from stock_analyzer.py and
stock_health_service.py into a single module.
"""

import logging
import re
import time
from typing import Any, Dict, Optional

import requests
from bs4 import BeautifulSoup

from constants import (
    ROE_EXCELLENT,
    ROE_GOOD,
    ROE_POOR,
    DE_LOW,
    DE_MODERATE,
    DE_HIGH,
    SCREENER_API_DELAY,
)

logger = logging.getLogger(__name__)

# Circuit breaker — trips after 3 consecutive Screener.in failures,
# recovers after 5 minutes.
from services.circuit_breaker import CircuitBreaker
_screener_cb = CircuitBreaker("screener.in", failure_threshold=3, recovery_timeout=300)

_SCREENER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
}


def _extract_ratio(soup: BeautifulSoup, ratio_name: str) -> Optional[float]:
    """Extract a specific ratio value from Screener.in HTML."""
    try:
        # Look in the top-ratios section first
        ratios_section = soup.find("ul", {"id": "top-ratios"})
        if ratios_section:
            for li in ratios_section.find_all("li"):
                text = li.get_text()
                if ratio_name.lower() in text.lower():
                    numbers = re.findall(r"[-+]?\d*\.?\d+", text)
                    if numbers:
                        return float(numbers[-1])

        # Fallback: search in full page text
        page_text = soup.get_text()
        if ratio_name.lower() in page_text.lower():
            lines = page_text.split("\n")
            for i, line in enumerate(lines):
                if ratio_name.lower() in line.lower():
                    search_text = " ".join(lines[i : min(i + 3, len(lines))])
                    numbers = re.findall(r"[-+]?\d*\.?\d+", search_text)
                    if numbers:
                        return float(numbers[0])
        return None
    except Exception as e:
        logger.debug(f"Error extracting {ratio_name}: {e}")
        return None


def _get_last_known_fundamentals(symbol: str) -> Dict[str, Optional[float]]:
    """Fallback: return the most recent cached fundamentals from the DB."""
    try:
        from services.db import get_conn
        conn = get_conn()
        try:
            row = conn.execute(
                "SELECT fund_roe, fund_debt_to_equity, fund_sales_growth "
                "FROM stock_analyses WHERE symbol = ? "
                "ORDER BY analyzed_at DESC LIMIT 1",
                (symbol,),
            ).fetchone()
            if row:
                logger.info("[Screener] Using DB fallback fundamentals for %s", symbol)
                return {
                    "roe": row["fund_roe"],
                    "debt_to_equity": row["fund_debt_to_equity"],
                    "sales_growth": row["fund_sales_growth"],
                }
        finally:
            conn.close()
    except Exception as db_err:
        logger.debug("[Screener] DB fallback failed for %s: %s", symbol, db_err)
    return {"roe": None, "debt_to_equity": None, "sales_growth": None}


def scrape_screener_ratios(symbol: str) -> Dict[str, Optional[float]]:
    """Scrape key financial ratios from Screener.in.

    Returns dict with keys: 'roe', 'debt_to_equity', 'sales_growth'.
    Values are None if unavailable.

    Uses a circuit breaker — if Screener.in has failed 3 times in a row the
    circuit opens and the DB cache is returned immediately without an HTTP call.
    The circuit resets after 5 minutes.
    """
    if not _screener_cb.is_call_permitted():
        logger.info("[Screener] Circuit open — returning DB fallback for %s", symbol)
        return _get_last_known_fundamentals(symbol)

    try:
        time.sleep(SCREENER_API_DELAY)

        url = f"https://www.screener.in/company/{symbol}/consolidated/"
        response = requests.get(url, headers=_SCREENER_HEADERS, timeout=15)
        response.raise_for_status()

        soup = BeautifulSoup(response.content, "html.parser")

        roe = _extract_ratio(soup, "ROE") or _extract_ratio(soup, "Return on Equity")
        debt_to_equity = (
            _extract_ratio(soup, "Debt to equity")
            or _extract_ratio(soup, "D/E")
            or _extract_ratio(soup, "Debt Equity")
        )
        sales_growth = (
            _extract_ratio(soup, "Sales growth")
            or _extract_ratio(soup, "Revenue growth")
            or _extract_ratio(soup, "Sales CAGR")
        )

        _screener_cb.record_success()
        return {
            "roe": roe,
            "debt_to_equity": debt_to_equity,
            "sales_growth": sales_growth,
        }

    except Exception as e:
        _screener_cb.record_failure()
        logger.warning(f"Screener.in scraping failed for {symbol}: {e}")
        return _get_last_known_fundamentals(symbol)


def score_fundamentals(
    roe: Optional[float] = None,
    debt_to_equity: Optional[float] = None,
    sales_growth: Optional[float] = None,
) -> Dict[str, Any]:
    """Score fundamentals based on ROE, D/E ratio, and sales growth.

    Returns dict with 'score' (1-5), 'summary' (human-readable string),
    and the raw ratio values.
    """
    score = 3  # Default neutral

    if roe is not None:
        if debt_to_equity is not None:
            if roe > ROE_EXCELLENT and debt_to_equity < DE_LOW:
                score = 5
            elif roe > ROE_GOOD and debt_to_equity < DE_MODERATE:
                score = 4
            elif roe < ROE_POOR or debt_to_equity > DE_HIGH:
                score = 1
            elif roe < ROE_GOOD or debt_to_equity > DE_MODERATE:
                score = 2
        else:
            if roe > ROE_EXCELLENT:
                score = 4
            elif roe > ROE_GOOD:
                score = 3
            elif roe < ROE_POOR:
                score = 2
    elif debt_to_equity is not None:
        if debt_to_equity < DE_LOW:
            score = 4
        elif debt_to_equity < DE_MODERATE:
            score = 3
        else:
            score = 2

    # Build summary
    parts = []
    if roe is not None:
        parts.append(f"ROE: {roe:.1f}%")
    if debt_to_equity is not None:
        parts.append(f"D/E: {debt_to_equity:.2f}")
    if sales_growth is not None:
        parts.append(f"Growth: {sales_growth:.1f}%")

    return {
        "score": score,
        "summary": ", ".join(parts) if parts else "Data unavailable",
        "roe": roe,
        "debt_to_equity": debt_to_equity,
        "sales_growth": sales_growth,
    }


def get_fundamental_analysis(symbol: str) -> Dict[str, Any]:
    """Full fundamental analysis: scrape ratios and score them.

    Convenience function combining scrape_screener_ratios + score_fundamentals.
    """
    ratios = scrape_screener_ratios(symbol)
    return score_fundamentals(**ratios)
