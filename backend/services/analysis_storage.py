"""Analysis storage service — SQLite-backed CRUD for cached stock analysis results.

Per-user analysis results are stored in the `user_analysis_cache` table
for thread-safe concurrent access (replaces the old JSON file approach).
"""

import json
import logging
from datetime import datetime
from typing import Any, Dict, Optional

from services.db import get_conn

logger = logging.getLogger(__name__)


def save_analysis_result(user_id: Any, symbol: str, analysis_data: Dict[str, Any]) -> None:
    """Save (upsert) analysis result for a user+symbol pair."""
    conn = get_conn()
    try:
        conn.execute(
            """
            INSERT INTO user_analysis_cache (user_id, symbol, analysis_json, saved_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(user_id, symbol) DO UPDATE SET
                analysis_json = excluded.analysis_json,
                saved_at = excluded.saved_at
            """,
            (int(user_id), symbol.upper(), json.dumps(analysis_data), datetime.now().isoformat()),
        )
        conn.commit()
    except Exception as e:
        logger.error("Error saving analysis for %s (user=%s): %s", symbol, user_id, e)
    finally:
        conn.close()


def get_all_audit_results(user_id: Any) -> list:
    """Get all cached audit results (type='audit') for a user, sorted by health_score asc."""
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT analysis_json, saved_at, symbol FROM user_analysis_cache WHERE user_id = ?",
            (int(user_id),),
        ).fetchall()
        results = []
        for row in rows:
            try:
                data = json.loads(row["analysis_json"])
                if data.get("type") == "audit":
                    results.append({
                        "symbol":   row["symbol"],
                        "saved_at": row["saved_at"],
                        "data":     data,
                    })
            except Exception:
                continue
        results.sort(key=lambda r: r["data"].get("health_score", 5.0))
        return results
    except Exception as e:
        logger.error("Error loading audit results for user=%s: %s", user_id, e)
        return []
    finally:
        conn.close()


def get_saved_analysis(user_id: Any, symbol: str) -> Optional[Dict[str, Any]]:
    """Get saved analysis result for a user+symbol pair."""
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT analysis_json, saved_at, symbol FROM user_analysis_cache WHERE user_id = ? AND symbol = ?",
            (int(user_id), symbol.upper()),
        ).fetchone()
        if row:
            logger.debug("Found saved analysis for %s (user=%s)", symbol, user_id)
            return {
                "analysis": json.loads(row["analysis_json"]),
                "saved_at": row["saved_at"],
                "symbol": row["symbol"],
            }
        return None
    except Exception as e:
        logger.error("Error loading analysis for %s (user=%s): %s", symbol, user_id, e)
        return None
    finally:
        conn.close()
