"""Shared Sector Agent — unified sector momentum enrichment and filtering.

Provides:
    enrich_with_sector(items, kite, .) — batch sector enrichment + optional filtering
"""

import json
import time
from datetime import datetime, timedelta
from typing import Callable, Optional

from agents.shared.data_infra import (
    resolve_instrument_tokens,
    load_sector_indices,
    get_sector_index_tokens,
    PipelineSession,
)
from constants import SECTOR_5D_TOLERANCE, SECTOR_HISTORY_CALENDAR_DAYS


def enrich_with_sector(
    items: list[dict],
    kite,
    log: Callable = print,
    mode: str = "enrich",
    tolerance: float = SECTOR_5D_TOLERANCE,
    include_3m: bool = True,
    session: Optional[PipelineSession] = None,
) -> list[dict]:
    """Add sector index performance data to each item.

    Each item must have 'symbol' and optionally 'sector_index' keys.

    Adds keys:
        sector_5d_change    (float or None)
        sector_3m_return    (float or None, only if include_3m=True)

    Args:
        mode: "enrich" — all items pass through (sector_5d_change may be 0.0/None if unavailable).
              "filter" — removes items where sector_5d_change < tolerance.
        tolerance: minimum allowed 5-day sector change (used only in "filter" mode).
        include_3m: whether to also compute 3-month sector return.
    """
    if not items:
        return []

    # Collect unique sector indices needed
    needed: set[str] = set()
    for item in items:
        si = item.get("sector_index")
        if si:
            needed.add(si)

    if not needed:
        log("No sector indices found for items — skipping sector enrichment")
        for item in items:
            item["sector_5d_change"] = None
            if include_3m:
                item["sector_3m_return"] = None
        return items

    # Resolve sector index instrument tokens
    # Use the already-cached instrument_map if available, otherwise fetch
    cached_map = session.instrument_map if session is not None else None
    if cached_map is None:
        from agents.shared.data_infra import _instrument_map as _global_map
        cached_map = _global_map
    if cached_map is None:
        instrument_map = resolve_instrument_tokens(kite, log, session=session)
    else:
        instrument_map = cached_map

    sector_token_map = get_sector_index_tokens(instrument_map)

    # Fetch 5-day and optionally 3M sector performance
    sector_change: dict[str, float] = {}
    sector_3m: dict[str, float] = {}

    # Use 90 calendar days to cover both 5 trading days and 63 trading days
    fetch_days = 90 if include_3m else SECTOR_HISTORY_CALENDAR_DAYS

    for idx_symbol in needed:
        token = sector_token_map.get(idx_symbol)
        if not token:
            log(f"  No token for {idx_symbol}, defaulting to 0.0")
            sector_change[idx_symbol] = 0.0
            if include_3m:
                sector_3m[idx_symbol] = 0.0
            continue
        try:
            to_date = datetime.now()
            from_date = to_date - timedelta(days=fetch_days)
            history = kite.historical_data(
                token,
                from_date.strftime("%Y-%m-%d"),
                to_date.strftime("%Y-%m-%d"),
                "day",
            )
            if history and len(history) >= 5:
                recent = history[-1]["close"]
                five_days_ago = history[-5]["close"]
                pct = ((recent - five_days_ago) / five_days_ago * 100) if five_days_ago > 0 else 0.0
                sector_change[idx_symbol] = round(pct, 2)
            elif history and len(history) >= 2:
                pct = ((history[-1]["close"] - history[0]["close"]) / history[0]["close"]) * 100
                sector_change[idx_symbol] = round(pct, 2)
            else:
                sector_change[idx_symbol] = 0.0

            if include_3m:
                if history and len(history) >= 63:
                    pct_3m = ((history[-1]["close"] - history[-63]["close"]) / history[-63]["close"]) * 100
                    sector_3m[idx_symbol] = round(pct_3m, 2)
                elif history and len(history) >= 2:
                    pct_3m = ((history[-1]["close"] - history[0]["close"]) / history[0]["close"]) * 100
                    sector_3m[idx_symbol] = round(pct_3m, 2)
                else:
                    sector_3m[idx_symbol] = 0.0

            time.sleep(0.35)
        except Exception as e:
            log(f"  Sector history failed for {idx_symbol}: {e}")
            sector_change[idx_symbol] = 0.0
            if include_3m:
                sector_3m[idx_symbol] = 0.0

    log(f"Sector 5-day changes: {json.dumps(sector_change)}")
    if include_3m:
        log(f"Sector 3M returns: {json.dumps(sector_3m)}")

    # Attach to items and optionally filter
    if mode == "filter":
        passed = []
        for item in items:
            si = item.get("sector_index", "")
            change = sector_change.get(si, 0.0)
            item["sector_5d_change"] = change
            if include_3m:
                item["sector_3m_return"] = sector_3m.get(si, 0.0) if si else None
            if change >= tolerance:
                passed.append(item)
        log(
            f"Sector filter: {len(passed)} / {len(items)} passed "
            f"(tolerance: {tolerance}%)"
        )
        return passed
    else:
        # enrich mode — all items pass through
        for item in items:
            si = item.get("sector_index")
            item["sector_5d_change"] = sector_change.get(si, 0.0) if si else None
            if include_3m:
                item["sector_3m_return"] = sector_3m.get(si, 0.0) if si else None
        return items
