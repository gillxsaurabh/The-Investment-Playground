"""CogniCap Backend — Flask Application Entry Point.

All route handlers are organized into Flask Blueprints under routes/.
Business logic lives in services/. Broker abstraction in broker/.
"""

from flask import Flask
from flask_cors import CORS

from config import FLASK_PORT, FLASK_DEBUG, validate_config
from logging_config import setup_logging
from routes import register_blueprints


def create_app():
    """Application factory — creates and configures the Flask app."""
    setup_logging()
    validate_config()

    app = Flask(__name__)
    CORS(app, origins=["http://localhost:4200"])

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

    return app


if __name__ == "__main__":
    app = create_app()
    app.run(debug=FLASK_DEBUG, port=FLASK_PORT)
