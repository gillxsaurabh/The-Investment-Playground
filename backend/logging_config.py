"""Structured logging setup for the CogniCap backend.

Outputs JSON lines when LOG_FORMAT=json (default), plain text otherwise.
Automatically injects request_id and user_id from Flask request context.
"""

import json
import logging
import sys
import time
from datetime import datetime, timezone


class _RequestContext(logging.Filter):
    """Injects request_id and user_id into log records from Flask's g when available."""

    def filter(self, record):
        try:
            from flask import has_request_context, g
            if has_request_context():
                record.request_id = getattr(g, "request_id", "-")
                record.user_id = getattr(g, "current_user", {}).get("id", "-") if hasattr(g, "current_user") and isinstance(getattr(g, "current_user", None), dict) else "-"
            else:
                record.request_id = "-"
                record.user_id = "-"
        except Exception:
            record.request_id = "-"
            record.user_id = "-"
        return True


class _JsonFormatter(logging.Formatter):
    """Format each log record as a single JSON line."""

    def format(self, record):
        self.formatException  # ensure exc_info is handled
        log = {
            "ts": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
            "request_id": getattr(record, "request_id", "-"),
            "user_id": getattr(record, "user_id", "-"),
        }
        if record.exc_info:
            log["exc"] = self.formatException(record.exc_info)
        return json.dumps(log, ensure_ascii=False)


class _TextFormatter(logging.Formatter):
    """Human-readable formatter with request context."""

    def __init__(self):
        super().__init__(
            fmt="%(asctime)s [%(levelname)s] %(name)s [req=%(request_id)s uid=%(user_id)s]: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )


def setup_logging(level=logging.INFO, json_format: bool = False):
    """Configure structured logging for the application.

    Args:
        level: Root log level.
        json_format: If True, emit JSON lines; else human-readable text.
    """
    import os
    if os.getenv("LOG_FORMAT", "").lower() == "json":
        json_format = True

    formatter = _JsonFormatter() if json_format else _TextFormatter()
    context_filter = _RequestContext()

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)
    handler.addFilter(context_filter)

    root = logging.getLogger()
    root.setLevel(level)
    # Avoid duplicate handlers on repeated calls (e.g. during tests)
    if not any(isinstance(h, logging.StreamHandler) and h.stream is sys.stdout for h in root.handlers):
        root.addHandler(handler)
    else:
        # Ensure existing handler has the filter
        for h in root.handlers:
            if isinstance(h, logging.StreamHandler):
                h.setFormatter(formatter)
                if not any(isinstance(f, _RequestContext) for f in h.filters):
                    h.addFilter(context_filter)

    # Suppress noisy libraries
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("kiteconnect").setLevel(logging.WARNING)
    logging.getLogger("werkzeug").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("apscheduler").setLevel(logging.INFO)

    return root
