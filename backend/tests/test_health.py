"""Tests for health check endpoints."""


def test_health_legacy(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.get_json()["status"] == "ok"


def test_liveness(client):
    resp = client.get("/health/live")
    assert resp.status_code == 200
    assert resp.get_json()["status"] == "live"


def test_readiness_ok(client):
    resp = client.get("/health/ready")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["status"] == "ready"
    assert data["checks"]["db"] == "ok"


def test_request_id_header(client):
    """Response must include X-Request-ID header."""
    resp = client.get("/health")
    assert "X-Request-ID" in resp.headers


def test_security_headers(client):
    """Key security headers must be present on all responses."""
    resp = client.get("/health")
    assert resp.headers["X-Content-Type-Options"] == "nosniff"
    assert resp.headers["X-Frame-Options"] == "DENY"


def test_metrics_unauthenticated(client):
    """Metrics endpoint requires authentication."""
    resp = client.get("/health/metrics")
    assert resp.status_code == 401


def test_metrics_authenticated(client, auth_headers):
    """Metrics endpoint returns runtime data when authenticated."""
    resp = client.get("/health/metrics", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.get_json()
    assert "uptime_seconds" in data
    assert "python_version" in data
    assert "db_size_bytes" in data
    assert "open_trades_count" in data


def test_error_includes_request_id(client):
    """Error responses should include request_id."""
    resp = client.get("/nonexistent-route")
    assert resp.status_code == 404
    data = resp.get_json()
    assert "request_id" in data
