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

    register_blueprints(app)

    return app


if __name__ == "__main__":
    app = create_app()
    app.run(debug=FLASK_DEBUG, port=FLASK_PORT)
