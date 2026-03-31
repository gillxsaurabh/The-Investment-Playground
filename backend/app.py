"""CogniCap Backend — Flask Application Entry Point.

All route handlers are organized into Flask Blueprints under routes/.
Business logic lives in services/. Broker abstraction in broker/.
"""

import atexit
import logging
import time
import uuid
from pathlib import Path

from flask import Flask, send_from_directory, request, jsonify, g
from flask_cors import CORS

from config import FLASK_PORT, FLASK_DEBUG, CORS_ORIGINS, SENTRY_DSN, validate_config
from extensions import limiter
from logging_config import setup_logging
from routes import register_blueprints

logger = logging.getLogger(__name__)

# Angular production build output (relative to this file)
FRONTEND_DIST = Path(__file__).parent.parent / "frontend" / "cognicap-app" / "dist" / "cognicap-app" / "browser"


def _init_sentry():
    """Initialize Sentry error tracking if SENTRY_DSN is configured."""
    if not SENTRY_DSN:
        return
    try:
        import sentry_sdk

        def _scrub_sensitive(event, hint):
            """Remove tokens and secrets from Sentry events."""
            sensitive_keys = {"access_token", "broker_token", "refresh_token", "JWT_SECRET", "password"}
            if "request" in event and "data" in event["request"]:
                data = event["request"]["data"]
                if isinstance(data, dict):
                    for key in sensitive_keys:
                        if key in data:
                            data[key] = "[REDACTED]"
            return event

        sentry_sdk.init(
            dsn=SENTRY_DSN,
            traces_sample_rate=0.1,
            send_default_pii=False,
            before_send=_scrub_sensitive,
        )
        logger.info("[App] Sentry initialized")
    except Exception as e:
        logger.warning("[App] Sentry init failed: %s", e)


def create_app(testing=False):
    """Application factory — creates and configures the Flask app."""
    setup_logging()
    validate_config()
    _init_sentry()

    app = Flask(
        __name__,
        static_folder=str(FRONTEND_DIST) if FRONTEND_DIST.exists() else None,
        static_url_path="",
    )

    if testing:
        app.config["TESTING"] = True
        app.config["RATELIMIT_ENABLED"] = False

    # --- CORS: whitelist specific origins ---
    CORS(app, origins=CORS_ORIGINS, supports_credentials=True)

    # --- Rate limiter ---
    limiter.init_app(app)

    # --- Request ID + timing ---
    @app.before_request
    def attach_request_context():
        g.request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())[:8]
        g.request_start = time.monotonic()

    # --- Security headers + request duration + request ID propagation ---
    @app.after_request
    def set_security_headers(response):
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        response.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; img-src 'self' data:; font-src 'self' https://fonts.gstatic.com; connect-src 'self'"
        response.headers["X-Request-ID"] = getattr(g, "request_id", "-")

        # Log request duration (skip noisy health/static)
        path = request.path
        if not path.startswith("/health"):
            duration_ms = round((time.monotonic() - getattr(g, "request_start", time.monotonic())) * 1000)
            logger.info("%s %s %s %dms", request.method, path, response.status_code, duration_ms)

        return response

    # --- Sanitize error responses (include request_id for debugging) ---
    def _rid():
        return getattr(g, "request_id", "-")

    @app.errorhandler(404)
    def not_found(e):
        # For non-API paths, serve the Angular SPA (handles browser back/forward and direct URL navigation)
        if not request.path.startswith("/api/") and FRONTEND_DIST.exists():
            return send_from_directory(str(FRONTEND_DIST), "index.html")
        return jsonify({"success": False, "error": "Not found", "request_id": _rid()}), 404

    @app.errorhandler(500)
    def internal_error(e):
        return jsonify({"success": False, "error": "Internal server error", "request_id": _rid()}), 500

    @app.errorhandler(429)
    def rate_limit_exceeded(e):
        return jsonify({"success": False, "error": "Rate limit exceeded. Try again later.", "request_id": _rid()}), 429

    # Initialize SQLite schema on every startup (idempotent)
    try:
        from services.db import init_db
        init_db()
    except Exception as e:
        logger.warning("[App] DB init failed: %s", e)

    # Auto-promote ADMIN_EMAIL to admin on startup (for Railway/Docker deploys without shell access)
    _admin_email = os.getenv("ADMIN_EMAIL", "").strip().lower()
    if _admin_email:
        try:
            from services.db import get_conn
            conn = get_conn()
            result = conn.execute(
                "UPDATE users SET is_admin = TRUE WHERE LOWER(email) = ?", (_admin_email,)
            )
            conn.commit()
            conn.close()
            if result.rowcount:
                logger.info("[App] Promoted %s to admin via ADMIN_EMAIL env var", _admin_email)
        except Exception as e:
            logger.warning("[App] ADMIN_EMAIL auto-promote failed: %s", e)

    register_blueprints(app)

    # Start the weekly automation scheduler (Monday 10:00 AM IST)
    try:
        from automation.scheduler import start_scheduler, shutdown_scheduler
        start_scheduler()
        atexit.register(shutdown_scheduler)
    except Exception as e:
        logger.warning("[App] Scheduler failed to start: %s", e)

    # Serve Angular SPA — catch-all for non-API routes
    if FRONTEND_DIST.exists():
        @app.route("/", defaults={"path": ""})
        @app.route("/<path:path>")
        def serve_spa(path):
            full_path = FRONTEND_DIST / path
            if path and full_path.exists():
                return send_from_directory(str(FRONTEND_DIST), path)
            return send_from_directory(str(FRONTEND_DIST), "index.html")

    return app


if __name__ == "__main__":
    app = create_app()
    app.run(debug=FLASK_DEBUG, host="0.0.0.0", port=FLASK_PORT)
