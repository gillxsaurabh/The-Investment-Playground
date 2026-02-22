"""Analysis storage service — JSON-based CRUD for cached stock analysis results.

Extracted from app.py to decouple persistence logic from the Flask layer.
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from config import ANALYSIS_STORAGE_FILE

logger = logging.getLogger(__name__)


def load_analysis_storage() -> Dict[str, Any]:
    """Load saved analysis results from file."""
    try:
        path = Path(ANALYSIS_STORAGE_FILE)
        if path.exists():
            with open(path, "r") as f:
                return json.load(f)
    except Exception as e:
        logger.error(f"Error loading analysis storage: {e}")
    return {}


def save_analysis_storage(data: Dict[str, Any]) -> None:
    """Save analysis results to file."""
    try:
        path = Path(ANALYSIS_STORAGE_FILE)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        logger.error(f"Error saving analysis storage: {e}")


def get_user_analysis_key(access_token: str, symbol: str) -> str:
    """Generate a unique key for user+symbol analysis data."""
    token_suffix = access_token[-8:] if len(access_token) > 8 else access_token
    return f"{token_suffix}_{symbol}"


def save_analysis_result(
    access_token: str, symbol: str, analysis_data: Dict[str, Any]
) -> None:
    """Save analysis result for a user+symbol pair."""
    storage = load_analysis_storage()
    key = get_user_analysis_key(access_token, symbol)

    storage[key] = {
        "analysis": analysis_data,
        "saved_at": datetime.now().isoformat(),
        "symbol": symbol,
    }

    save_analysis_storage(storage)


def get_saved_analysis(
    access_token: str, symbol: str
) -> Optional[Dict[str, Any]]:
    """Get saved analysis result for a user+symbol pair."""
    storage = load_analysis_storage()
    key = get_user_analysis_key(access_token, symbol)
    result = storage.get(key)

    if result:
        logger.debug(f"Found saved analysis for {symbol}")
    else:
        logger.debug(f"No saved analysis found for {symbol}")

    return result
