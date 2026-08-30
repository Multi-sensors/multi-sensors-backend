from fastapi.testclient import TestClient

from main import app

client = TestClient(app)


def test_index():
    response = client.get("/")
    assert response.status_code == 200
    assert response.json() == {"hello": "world"}


def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_about():
    response = client.get("/about")
    assert response.status_code == 200
    assert response.json() == "Multi sensor research project backend"
