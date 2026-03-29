"""Health check endpoints.

GET /health         — legacy alias, returns {"status": "ok"}
GET /health/live    — liveness: always 200 if the process is running
GET /health/ready   — readiness: checks DB connectivity
GET /health/metrics — runtime metrics (authenticated)
"""

import logging
import os
import sys
import time
from pathlib import Path

from flask import Blueprint, jsonify, send_file

from middleware.auth import require_auth

logger = logging.getLogger(__name__)
health_bp = Blueprint("health", __name__)

_start_time = time.monotonic()


@health_bp.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"})


@health_bp.route("/health/live", methods=["GET"])
def liveness():
    """Liveness probe — returns 200 if the process is alive."""
    return jsonify({"status": "live"}), 200


@health_bp.route("/health/ready", methods=["GET"])
def readiness():
    """Readiness probe — checks DB is reachable before accepting traffic."""
    checks = {}
    ok = True

    # SQLite connectivity check
    try:
        from services.db import get_conn
        conn = get_conn()
        conn.execute("SELECT 1").fetchone()
        conn.close()
        checks["db"] = "ok"
    except Exception as e:
        logger.warning(f"[Health] DB check failed: {e}")
        checks["db"] = "error"
        ok = False

    status = "ready" if ok else "not_ready"
    http_status = 200 if ok else 503
    return jsonify({"status": status, "checks": checks}), http_status


@health_bp.route("/health/metrics", methods=["GET"])
@require_auth
def metrics():
    """Runtime metrics — requires authentication."""
    data = {
        "uptime_seconds": round(time.monotonic() - _start_time),
        "python_version": sys.version.split()[0],
    }

    # DB size
    try:
        from config import DB_PATH
        data["db_size_bytes"] = os.path.getsize(str(DB_PATH))
    except Exception:
        data["db_size_bytes"] = None

    # Open trades count
    try:
        from services.db import get_conn
        conn = get_conn()
        row = conn.execute("SELECT COUNT(*) as cnt FROM trades WHERE status='OPEN'").fetchone()
        conn.close()
        data["open_trades_count"] = row["cnt"] if row else 0
    except Exception:
        data["open_trades_count"] = None

    # Scheduler status
    try:
        from automation.scheduler import is_running, get_next_run_time
        data["scheduler_running"] = is_running()
        data["scheduler_next_run"] = get_next_run_time()
    except Exception:
        data["scheduler_running"] = None
        data["scheduler_next_run"] = None

    return jsonify(data), 200


@health_bp.route("/api/docs", methods=["GET"])
def api_docs():
    """Serve the OpenAPI spec as YAML."""
    spec_path = Path(__file__).resolve().parent.parent / "openapi.yaml"
    if not spec_path.exists():
        return jsonify({"error": "OpenAPI spec not found"}), 404
    return send_file(str(spec_path), mimetype="text/yaml")
