from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from supabase import AuthApiError

import main
from main import app

client = TestClient(app)

LOGIN_URL = "/api/v1/auth/login"


@pytest.fixture
def sign_in(monkeypatch):
    """Replace the Supabase call with a stub, and hand back the recorded arguments."""
    calls = []

    def install(result=None, error=None):
        def fake_sign_in(credentials):
            calls.append(credentials)
            if error is not None:
                raise error
            return result

        monkeypatch.setattr(main.supabase.auth, "sign_in_with_password", fake_sign_in)
        return calls

    return install


@pytest.fixture
def sign_out(monkeypatch):
    """Record sign-out calls so the 403 path can be checked without network access."""
    calls = []
    monkeypatch.setattr(main.supabase.auth, "sign_out", lambda *a, **kw: calls.append(True))
    return calls


def make_result(user_id=main.ALLOWED_SUPABASE_USER_ID):
    session = SimpleNamespace(
        access_token="access-abc",
        refresh_token="refresh-xyz",
        expires_in=3600,
    )
    user = SimpleNamespace(id=user_id, email="person@example.com")
    return SimpleNamespace(session=session, user=user)


def test_login_success(sign_in):
    calls = sign_in(result=make_result())

    response = client.post(
        LOGIN_URL, json={"email": "person@example.com", "password": "hunter2"}
    )

    assert response.status_code == 200
    assert calls == [{"email": "person@example.com", "password": "hunter2"}]
    assert response.json() == {
        "access_token": "access-abc",
        "refresh_token": "refresh-xyz",
        "token_type": "bearer",
        "expires_in": 3600,
        "user": {
            "id": "user-123",
            "email": "person@example.com"
        }
    }


def test_login_with_bad_credentials(sign_in):
    sign_in(error=AuthApiError("Invalid login credentials", 400, "invalid_credentials"))

    response = client.post(
        LOGIN_URL, json={"email": "person@example.com", "password": "wrong"}
    )

    assert response.status_code == 401
    assert response.json() == {"detail": "Invalid email or password"}


def test_login_without_session(sign_in):
    sign_in(result=SimpleNamespace(session=None, user=None))

    response = client.post(
        LOGIN_URL, json={"email": "person@example.com", "password": "hunter2"}
    )

    assert response.status_code == 401


def test_login_as_unapproved_user(sign_in, sign_out):
    """Valid credentials for an account that is not the configured sole user."""
    sign_in(result=make_result(user_id="some-other-user"))

    response = client.post(
        LOGIN_URL, json={"email": "intruder@example.com", "password": "hunter2"}
    )

    assert response.status_code == 403
    assert response.json() == {"detail": "Account is not authorized"}
    assert sign_out == [True]


def test_login_as_unapproved_user_leaks_no_tokens(sign_in, sign_out):
    sign_in(result=make_result(user_id="some-other-user"))

    response = client.post(
        LOGIN_URL, json={"email": "intruder@example.com", "password": "hunter2"}
    )

    body = response.text
    assert "access-abc" not in body
    assert "refresh-xyz" not in body


def test_login_rejects_unapproved_user_even_when_sign_out_fails(sign_in, monkeypatch):
    """A failed cleanup call must not downgrade the 403 into a 500."""
    sign_in(result=make_result(user_id="some-other-user"))

    def boom(*args, **kwargs):
        raise AuthApiError("sign out failed", 500, "unexpected_failure")

    monkeypatch.setattr(main.supabase.auth, "sign_out", boom)

    response = client.post(
        LOGIN_URL, json={"email": "intruder@example.com", "password": "hunter2"}
    )

    assert response.status_code == 403


def test_login_with_missing_fields():
    response = client.post(LOGIN_URL, json={"email": "person@example.com"})
    assert response.status_code == 422
