import httpx
import pytest
from fastapi.testclient import TestClient
from jose import jwt
from supabase import AuthApiError

import main
from auth import SUPABASE_JWT_SECRET
from main import app

client = TestClient(app)


def make_token(**claims):
    payload = {
        "sub": main.ALLOWED_SUPABASE_USER_ID,
        "email": "person@example.com",
        "aud": "authenticated",
    }
    payload.update(claims)
    return jwt.encode(payload, SUPABASE_JWT_SECRET, algorithm="HS256")


@pytest.fixture
def auth_header():
    return {"Authorization": f"Bearer {make_token()}"}


def fake_http_response(method, url, status_code):
    return httpx.Response(status_code, request=httpx.Request(method, url))


# --- logout ---


def test_logout_without_token():
    response = client.post("/api/v1/auth/logout")
    assert response.status_code == 401


def test_logout_success(monkeypatch, auth_header):
    calls = []

    def fake_post(url, params=None, headers=None, timeout=None):
        calls.append((url, params, headers))
        return fake_http_response("POST", url, 204)

    monkeypatch.setattr(main.httpx, "post", fake_post)

    response = client.post("/api/v1/auth/logout", headers=auth_header)

    assert response.status_code == 204
    assert calls[0][0] == f"{main.SUPABASE_AUTH_URL}/logout"
    assert calls[0][2]["Authorization"] == auth_header["Authorization"]


def test_logout_upstream_failure(monkeypatch, auth_header):
    def fake_post(url, params=None, headers=None, timeout=None):
        return fake_http_response("POST", url, 500)

    monkeypatch.setattr(main.httpx, "post", fake_post)

    response = client.post("/api/v1/auth/logout", headers=auth_header)

    assert response.status_code == 502


# --- password reset: request (forgot password, unauthenticated) ---


def test_password_reset_request_returns_202(monkeypatch):
    calls = []

    def fake_reset(email, options=None):
        calls.append((email, options))

    monkeypatch.setattr(main.supabase.auth, "reset_password_for_email", fake_reset)

    response = client.post(
        "/api/v1/auth/password-reset/request", json={"email": "person@example.com"}
    )

    assert response.status_code == 202
    assert calls == [("person@example.com", None)]


def test_password_reset_request_does_not_leak_unknown_email(monkeypatch):
    def fake_reset(email, options=None):
        raise AuthApiError("User not found", 400, "user_not_found")

    monkeypatch.setattr(main.supabase.auth, "reset_password_for_email", fake_reset)

    response = client.post(
        "/api/v1/auth/password-reset/request", json={"email": "nobody@example.com"}
    )

    assert response.status_code == 202
    assert "registered" in response.json()["detail"]


# --- password reset: confirm (authenticated) ---


def test_password_reset_confirm_without_token():
    response = client.post(
        "/api/v1/auth/password-reset/confirm",
        json={"new_password": "newpass123", "confirm_password": "newpass123"},
    )
    assert response.status_code == 401


def test_password_reset_confirm_mismatch(auth_header):
    response = client.post(
        "/api/v1/auth/password-reset/confirm",
        json={"new_password": "newpass123", "confirm_password": "different"},
        headers=auth_header,
    )
    assert response.status_code == 400
    assert response.json() == {"detail": "Passwords do not match"}


def test_password_reset_confirm_success(monkeypatch, auth_header):
    calls = []

    def fake_put(url, json=None, headers=None, timeout=None):
        calls.append((url, json, headers))
        return fake_http_response("PUT", url, 200)

    monkeypatch.setattr(main.httpx, "put", fake_put)

    response = client.post(
        "/api/v1/auth/password-reset/confirm",
        json={"new_password": "newpass123", "confirm_password": "newpass123"},
        headers=auth_header,
    )

    assert response.status_code == 204
    assert calls[0][1] == {"password": "newpass123"}


def test_password_reset_confirm_rejected_by_supabase(monkeypatch, auth_header):
    def fake_put(url, json=None, headers=None, timeout=None):
        return fake_http_response("PUT", url, 422)

    monkeypatch.setattr(main.httpx, "put", fake_put)

    response = client.post(
        "/api/v1/auth/password-reset/confirm",
        json={"new_password": "short", "confirm_password": "short"},
        headers=auth_header,
    )

    assert response.status_code == 400
