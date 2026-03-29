"""Gunicorn configuration for CogniCap production deployment.

- workers=1: SQLite is single-writer, APScheduler runs in-process,
  rate limiter uses in-memory storage. Multiple workers would cause
  duplicate schedulers, rate-limiter bypass, and write contention.
- threads=4: Safe concurrency via GIL + SQLite WAL mode.
- timeout=300: Stock analysis endpoints involve multiple LLM API calls.
"""

import os

bind = f"0.0.0.0:{os.getenv('PORT', '5000')}"
workers = 1
threads = 4
timeout = 300
accesslog = "-"
preload_app = True
