"""Shared News Agent — unified Google News RSS fetching.

Provides:
    fetch_news_headlines(symbol, days) — fetch headlines for a single symbol
    fetch_news_batch(symbols, days, .) — parallel batch fetch, returns symbol → headlines dict
"""

import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from email.utils import parsedate_to_datetime
from typing import Callable

import requests

from constants import NEWS_LOOKBACK_DAYS


def fetch_news_headlines(
    symbol: str,
    days: int = NEWS_LOOKBACK_DAYS,
) -> list[dict]:
    """Fetch recent news headlines from Google News RSS for a stock.

    Returns list of dicts with 'title', 'published' keys (max 10).
    """
    try:
        url = (
            f"https://news.google.com/rss/search?q={symbol}+NSE+stock"
            "&hl=en-IN&gl=IN&ceid=IN:en"
        )
        resp = requests.get(
            url,
            headers={"User-Agent": "Mozilla/5.0 (compatible; CogniCap/1.0)"},
            timeout=10,
        )
        resp.raise_for_status()

        root = ET.fromstring(resp.content)
        cutoff = datetime.now() - timedelta(days=days)
        headlines = []

        for item in root.findall(".//item"):
            title_el = item.find("title")
            pub_el = item.find("pubDate")
            if title_el is None:
                continue
            title = title_el.text or ""

            if pub_el is not None and pub_el.text:
                try:
                    pub_date = parsedate_to_datetime(pub_el.text)
                    if pub_date.replace(tzinfo=None) < cutoff:
                        continue
                except Exception:
                    pass

            headlines.append({
                "title": title,
                "published": pub_el.text if pub_el is not None else None,
            })
            if len(headlines) >= 10:
                break

        return headlines
    except Exception as e:
        print(f"[NewsAgent] News fetch failed for {symbol}: {e}")
        return []


def fetch_news_batch(
    symbols: list[str],
    days: int = NEWS_LOOKBACK_DAYS,
    max_workers: int = 5,
    log: Callable = print,
) -> dict[str, list[dict]]:
    """Parallel news fetch for multiple symbols.

    Returns dict mapping symbol → list of headline dicts.
    """
    log(f"Fetching news for {len(symbols)} symbols...")
    news_map: dict[str, list[dict]] = {}

    def _fetch(symbol: str):
        return symbol, fetch_news_headlines(symbol, days=days)

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [executor.submit(_fetch, sym) for sym in symbols]
        for future in as_completed(futures):
            sym, headlines = future.result()
            news_map[sym] = headlines

    log(f"News fetch complete: {len(news_map)} symbols processed")
    return news_map
