"""Shared Fundamentals Agent — unified Screener.in scraping and batch enrichment.

Provides:
    scrape_fundamentals(symbol)        — single HTTP request to Screener.in
    enrich_with_fundamentals(items, .) — parallel batch enrichment + optional filtering
"""

import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Callable, Optional

import requests
from bs4 import BeautifulSoup

from constants import (
    STRICT_ROE_MIN,
    STRICT_DE_MAX,
    YOY_QUARTERS_NEEDED,
)

_SCREENER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
}


def _parse_number(text: str) -> Optional[float]:
    """Parse a number string like '1,234.56' or '-456' from Screener.in."""
    try:
        cleaned = text.strip().replace(",", "").replace("%", "")
        if not cleaned or cleaned == "--":
            return None
        return float(cleaned)
    except (ValueError, AttributeError):
        return None


def scrape_fundamentals(symbol: str) -> dict:
    """Scrape Screener.in for quarterly profits, ROE, D/E.

    Returns dict with keys:
        profit_values                  (list[float], oldest first)
        roe                            (float or None)
        debt_to_equity                 (float or None)
        sales_growth                   (float or None)
        consecutive_decline_quarters   (int)
        qoq_declining                  (bool)
        yoy_declining                  (bool or None)
        yoy_growing                    (bool or None)
        qoq_growing                    (bool)
        current_q_profit               (float or None)
        yoy_q_profit                   (float or None)
        previous_q_profit              (float or None)
        quarterly_profit_positive      (bool)
    """
    result = {
        "profit_values": [],
        "roe": None,
        "debt_to_equity": None,
        "sales_growth": None,
        "consecutive_decline_quarters": 0,
        "qoq_declining": False,
        "yoy_declining": None,
        "yoy_growing": None,
        "qoq_growing": False,
        "current_q_profit": None,
        "yoy_q_profit": None,
        "previous_q_profit": None,
        "quarterly_profit_positive": False,
    }

    try:
        time.sleep(1.0)
        url = f"https://www.screener.in/company/{symbol}/consolidated/"
        resp = requests.get(url, headers=_SCREENER_HEADERS, timeout=15)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.content, "html.parser")

        # --- Quarterly profits ---
        for section in soup.find_all("section"):
            heading = section.find(["h2", "h3"])
            if not heading or "quarter" not in heading.get_text().lower():
                continue
            table = section.find("table")
            if not table:
                continue
            for row in table.find_all("tr"):
                cells = row.find_all(["th", "td"])
                if not cells:
                    continue
                label = cells[0].get_text().strip().lower()
                if "net profit" in label or "profit after tax" in label:
                    values = [_parse_number(c.get_text()) for c in cells[1:]]
                    values = [v for v in values if v is not None]
                    result["profit_values"] = values

                    if values:
                        result["quarterly_profit_positive"] = values[-1] > 0

                    if len(values) >= 2:
                        result["qoq_declining"] = values[-1] < values[-2]
                        result["qoq_growing"] = values[-1] > values[-2]
                        result["current_q_profit"] = values[-1]
                        result["previous_q_profit"] = values[-2]

                    if len(values) >= YOY_QUARTERS_NEEDED:
                        result["yoy_declining"] = values[-1] < values[-5]
                        result["yoy_growing"] = values[-1] > values[-5]
                        result["yoy_q_profit"] = values[-5]

                    # Count consecutive declining quarters
                    decline_count = 0
                    for i in range(len(values) - 1, 0, -1):
                        if values[i] < values[i - 1]:
                            decline_count += 1
                        else:
                            break
                    result["consecutive_decline_quarters"] = decline_count
                    break
            break

        # --- ROE, D/E, Sales Growth via services.fundamentals ---
        try:
            from services.fundamentals import scrape_screener_ratios
            ratios = scrape_screener_ratios(symbol)
            result["roe"] = ratios.get("roe")
            result["debt_to_equity"] = ratios.get("debt_to_equity")
            result["sales_growth"] = ratios.get("sales_growth")
        except Exception:
            # Fallback: try to parse ROE from the already-fetched soup
            try:
                for li in soup.find_all("li", class_=lambda c: c and "flex" in c):
                    text = li.get_text(separator=" ").strip()
                    if "Return on equity" in text or "ROE" in text:
                        for span in li.find_all("span"):
                            val = _parse_number(span.get_text())
                            if val is not None:
                                result["roe"] = val
                                break
            except Exception:
                pass

    except Exception as e:
        print(f"[FundamentalsAgent] Screener.in failed for {symbol}: {e}")

    return result


def enrich_with_fundamentals(
    items: list[dict],
    log: Callable = print,
    mode: str = "enrich",
    max_workers: int = 6,
    session=None,
) -> list[dict]:
    """Parallel Screener.in enrichment for a list of stock/holding dicts.

    Each item must have a 'symbol' key.

    Mode options:
        "enrich"          — adds fields, no filtering (all items pass through)
        "filter_none"     — alias for "enrich"
        "filter_strict"   — YoY profit growing + ROE >= STRICT_ROE_MIN + D/E <= STRICT_DE_MAX
        "filter_standard" — YoY profit growing (fallback to QoQ if < 5 quarters)
        "filter_loose"    — latest quarterly profit > 0

    Adds fields to each item:
        roe, debt_to_equity, profit_values,
        profit_declining_quarters, qoq_declining, yoy_declining,
        quarterly_profit_growth, profit_yoy_growing, profit_qoq_growing,
        quarterly_profit_positive
    """
    is_filter_mode = mode not in ("enrich", "filter_none")
    log(f"Scraping Screener.in for {len(items)} items (mode={mode}, workers={max_workers})...")
    enriched_count = [0]

    def process_one(item: dict) -> Optional[dict]:
        symbol = item["symbol"]
        data = scrape_fundamentals(symbol)

        # Always attach the raw scraped fields
        item["roe"] = data.get("roe")
        item["debt_to_equity"] = data.get("debt_to_equity")
        item["profit_declining_quarters"] = data.get("consecutive_decline_quarters", 0)
        item["qoq_declining"] = data.get("qoq_declining", False)
        item["yoy_declining"] = data.get("yoy_declining")

        # Compute compound fields for buy pipeline compatibility
        yoy_growing = data.get("yoy_growing")
        qoq_growing = data.get("qoq_growing", False)
        profit_values = data.get("profit_values", [])

        item["profit_values"] = profit_values
        item["profit_qoq_growing"] = qoq_growing

        # Determine profit_yoy_growing (mirrors tools.py logic)
        if yoy_growing is True:
            item["profit_yoy_growing"] = True
            item["quarterly_profit_growth"] = True
        elif yoy_growing is None and qoq_growing:
            item["profit_yoy_growing"] = None  # YoY unavailable, QoQ passed
            item["quarterly_profit_growth"] = True
        else:
            item["profit_yoy_growing"] = False
            item["quarterly_profit_growth"] = False

        item["quarterly_profit_positive"] = data.get("quarterly_profit_positive", False)

        roe_str = f"ROE={item['roe']:.1f}%" if item["roe"] is not None else "ROE=N/A"
        log(
            f"  {symbol}: {roe_str}, D/E={item.get('debt_to_equity', 'N/A')}, "
            f"consecutive declining quarters={item['profit_declining_quarters']}, "
            f"QoQ declining={item['qoq_declining']}"
        )
        enriched_count[0] += 1

        # Apply filter if needed
        if is_filter_mode:
            if mode == "filter_strict":
                if not (yoy_growing is True or (yoy_growing is None and qoq_growing)):
                    return None
                roe = item.get("roe")
                de = item.get("debt_to_equity")
                if roe is None or roe < STRICT_ROE_MIN:
                    return None
                if de is not None and de > STRICT_DE_MAX:
                    return None

            elif mode == "filter_standard":
                if not (yoy_growing is True or (yoy_growing is None and qoq_growing)):
                    return None

            elif mode == "filter_loose":
                if not data.get("quarterly_profit_positive", False):
                    return None

        return item

    results = []
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(process_one, item): item["symbol"] for item in items}
        done_count = 0
        for future in as_completed(futures):
            done_count += 1
            result = future.result()
            if result is not None:
                results.append(result)
            if done_count % 5 == 0:
                log(f"Fundamentals: {done_count} / {len(items)} checked")

    if is_filter_mode:
        log(
            f"Fundamentals filter ({mode}): {len(results)} passed, "
            f"{len(items) - len(results)} removed"
        )
    else:
        log(f"Fundamentals scan complete: {enriched_count[0]} / {len(items)} processed")
    return results
