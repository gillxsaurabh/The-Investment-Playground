"""Tests for auth endpoints: register, login, refresh, me."""

import json


def _post(client, path, body):
    return client.post(path, data=json.dumps(body), content_type="application/json")


class TestRegister:
    def test_register_success(self, client):
        resp = _post(client, "/api/auth/register", {
            "email": "new@example.com",
            "password": "ValidPass1!",
            "name": "Alice",
        })
        assert resp.status_code == 201
        data = resp.get_json()
        assert data["success"] is True
        assert "access_token" in data
        assert "refresh_token" in data
        assert data["user"]["email"] == "new@example.com"

    def test_register_duplicate_email(self, client):
        payload = {"email": "dup@example.com", "password": "ValidPass1!", "name": "Bob"}
        _post(client, "/api/auth/register", payload)
        resp = _post(client, "/api/auth/register", payload)
        assert resp.status_code == 409

    def test_register_invalid_email(self, client):
        resp = _post(client, "/api/auth/register", {
            "email": "notanemail",
            "password": "ValidPass1!",
            "name": "Charlie",
        })
        assert resp.status_code == 400
        data = resp.get_json()
        assert data["code"] == "VALIDATION_ERROR"

    def test_register_short_password(self, client):
        resp = _post(client, "/api/auth/register", {
            "email": "short@example.com",
            "password": "abc",
            "name": "Dave",
        })
        assert resp.status_code == 400
        assert resp.get_json()["code"] == "VALIDATION_ERROR"

    def test_register_missing_fields(self, client):
        resp = _post(client, "/api/auth/register", {"email": "x@x.com"})
        assert resp.status_code == 400


class TestLogin:
    def test_login_success(self, client, registered_user):
        resp = _post(client, "/api/auth/login", {
            "email": registered_user["email"],
            "password": registered_user["password"],
        })
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"] is True
        assert "access_token" in data

    def test_login_wrong_password(self, client, registered_user):
        resp = _post(client, "/api/auth/login", {
            "email": registered_user["email"],
            "password": "WrongPassword!",
        })
        assert resp.status_code == 401

    def test_login_unknown_email(self, client):
        resp = _post(client, "/api/auth/login", {
            "email": "nobody@example.com",
            "password": "AnyPass123!",
        })
        assert resp.status_code == 401

    def test_login_missing_body(self, client):
        resp = _post(client, "/api/auth/login", {})
        assert resp.status_code == 400


class TestRefreshAndMe:
    def test_refresh_success(self, client, registered_user):
        resp = _post(client, "/api/auth/refresh", {
            "refresh_token": registered_user["refresh_token"],
        })
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"] is True
        assert "access_token" in data

    def test_refresh_invalid_token(self, client):
        resp = _post(client, "/api/auth/refresh", {"refresh_token": "invalid.token.value"})
        assert resp.status_code == 401

    def test_me_authenticated(self, client, registered_user, auth_headers):
        resp = client.get("/api/auth/me", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["user"]["email"] == registered_user["email"]

    def test_me_unauthenticated(self, client):
        resp = client.get("/api/auth/me")
        assert resp.status_code == 401
