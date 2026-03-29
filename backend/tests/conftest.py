"""Shared pytest fixtures for CogniCap backend tests."""

import os
import tempfile
import pytest

# Ensure JWT_SECRET is set before importing anything Flask-related
os.environ.setdefault("JWT_SECRET", "test-secret-key-for-unit-tests-only-minimum-32-chars")
os.environ.setdefault("KITE_API_KEY", "test_key")
os.environ.setdefault("KITE_API_SECRET", "test_secret")


@pytest.fixture(scope="session")
def app():
    """Create a Flask test application with an isolated in-memory SQLite DB."""
    import config as cfg
    # Point DB to a temp file for tests
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    cfg.DB_PATH = tmp.name

    from app import create_app
    application = create_app(testing=True)
    application.config["WTF_CSRF_ENABLED"] = False

    yield application

    os.unlink(tmp.name)


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture(scope="session")
def registered_user(app):
    """Register a test user and return login credentials + tokens."""
    import json
    client = app.test_client()
    resp = client.post(
        "/api/auth/register",
        data=json.dumps({"email": "ci@test.com", "password": "TestPass123!", "name": "CI User"}),
        content_type="application/json",
    )
    assert resp.status_code == 201, f"Registration failed: {resp.get_json()}"
    data = resp.get_json()
    return {
        "email": "ci@test.com",
        "password": "TestPass123!",
        "user": data["user"],
        "access_token": data["access_token"],
        "refresh_token": data["refresh_token"],
    }


@pytest.fixture(scope="session")
def auth_headers(registered_user):
    """Return Authorization headers for the registered test user."""
    return {"Authorization": f"Bearer {registered_user['access_token']}"}
