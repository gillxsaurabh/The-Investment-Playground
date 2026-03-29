"""Tests for password change and reset endpoints."""

import json


def _post(client, path, body, headers=None):
    return client.post(
        path, data=json.dumps(body), content_type="application/json", headers=headers,
    )


class TestChangePassword:
    def test_change_password_success(self, client, registered_user, auth_headers):
        resp = _post(client, "/api/auth/change-password", {
            "current_password": registered_user["password"],
            "new_password": "NewSecurePass456!",
        }, headers=auth_headers)
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"] is True

        # Old password should no longer work for login
        resp2 = _post(client, "/api/auth/login", {
            "email": registered_user["email"],
            "password": registered_user["password"],
        })
        assert resp2.status_code == 401

        # New password should work
        resp3 = _post(client, "/api/auth/login", {
            "email": registered_user["email"],
            "password": "NewSecurePass456!",
        })
        assert resp3.status_code == 200

        # Restore original password for other tests
        new_tokens = resp3.get_json()
        new_headers = {"Authorization": f"Bearer {new_tokens['access_token']}"}
        _post(client, "/api/auth/change-password", {
            "current_password": "NewSecurePass456!",
            "new_password": registered_user["password"],
        }, headers=new_headers)

    def test_change_password_wrong_current(self, client, auth_headers):
        resp = _post(client, "/api/auth/change-password", {
            "current_password": "WrongPassword!",
            "new_password": "NewSecurePass456!",
        }, headers=auth_headers)
        assert resp.status_code == 400

    def test_change_password_short_new(self, client, auth_headers):
        resp = _post(client, "/api/auth/change-password", {
            "current_password": "TestPass123!",
            "new_password": "short",
        }, headers=auth_headers)
        assert resp.status_code == 400

    def test_change_password_unauthenticated(self, client):
        resp = _post(client, "/api/auth/change-password", {
            "current_password": "test",
            "new_password": "NewSecurePass456!",
        })
        assert resp.status_code == 401


class TestForgotPassword:
    def test_forgot_password_existing_email(self, client, registered_user):
        resp = _post(client, "/api/auth/forgot-password", {
            "email": registered_user["email"],
        })
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"] is True

    def test_forgot_password_unknown_email(self, client):
        """Should still return 200 to prevent email enumeration."""
        resp = _post(client, "/api/auth/forgot-password", {
            "email": "nonexistent@example.com",
        })
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"] is True

    def test_forgot_password_empty_email(self, client):
        resp = _post(client, "/api/auth/forgot-password", {"email": ""})
        assert resp.status_code == 400


class TestResetPassword:
    def test_reset_password_invalid_token(self, client):
        resp = _post(client, "/api/auth/reset-password", {
            "token": "invalid-token-value-that-is-long-enough",
            "new_password": "NewSecurePass456!",
        })
        assert resp.status_code == 400

    def test_reset_password_short_password(self, client):
        resp = _post(client, "/api/auth/reset-password", {
            "token": "some-valid-looking-token-that-is-long",
            "new_password": "short",
        })
        assert resp.status_code == 400
