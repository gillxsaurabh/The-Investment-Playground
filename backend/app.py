"""CogniCap Backend — Flask Application Entry Point.

All route handlers are organized into Flask Blueprints under routes/.
Business logic lives in services/. Broker abstraction in broker/.
"""

import os
from pathlib import Path

from flask import Flask, send_from_directory
from flask_cors import CORS

from config import FLASK_PORT, FLASK_DEBUG, validate_config
from logging_config import setup_logging
from routes import register_blueprints

# Angular production build output (relative to this file)
FRONTEND_DIST = Path(__file__).parent.parent / "frontend" / "cognicap-app" / "dist" / "cognicap-app" / "browser"


def create_app():
    """Application factory — creates and configures the Flask app."""
    setup_logging()
    validate_config()

    app = Flask(
        __name__,
        static_folder=str(FRONTEND_DIST) if FRONTEND_DIST.exists() else None,
        static_url_path="",
    )
    CORS(app, origins="*")  # allow all origins — public demo app

    # Initialize SQLite schema on every startup (idempotent)
    try:
        from services.db import init_db
        init_db()
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(f"[App] DB init failed: {e}")

    register_blueprints(app)

    # Start the weekly automation scheduler (Monday 9:00 AM IST)
    try:
        from automation.scheduler import start_scheduler
        start_scheduler()
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(f"[App] Scheduler failed to start: {e}")

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
