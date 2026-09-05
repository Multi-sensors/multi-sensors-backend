from fastapi.testclient import TestClient
from jose import jwt

from auth import SUPABASE_JWT_SECRET
from main import app

client = TestClient(app)


def make_token(**claims):
    payload = {"sub": "user-123", "email": "person@example.com", "aud": "authenticated"}
    payload.update(claims)
    return jwt.encode(payload, SUPABASE_JWT_SECRET, algorithm="HS256")


def test_me_without_token():
    response = client.get("/api/v1/me")
    assert response.status_code == 401


def test_me_with_malformed_header():
    response = client.get("/api/v1/me", headers={"Authorization": "Token abc"})
    assert response.status_code == 401


def test_me_with_invalid_token():
    response = client.get("/api/v1/me", headers={"Authorization": "Bearer not-a-real-token"})
    assert response.status_code == 401


def test_me_with_valid_token():
    token = make_token()
    response = client.get("/api/v1/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    assert response.json() == {"user_id": "user-123", "email": "person@example.com"}
