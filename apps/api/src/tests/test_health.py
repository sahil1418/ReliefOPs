"""Smoke test for COMMIT 1 — verifies /health returns the success envelope."""
from fastapi.testclient import TestClient

from src.main import app

client = TestClient(app)


def test_health_returns_ok() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["error"] is None
    assert body["data"]["status"] == "ok"
    assert body["data"]["service"] == "relief-api"


def test_root_returns_envelope() -> None:
    response = client.get("/")
    assert response.status_code == 200
    body = response.json()
    assert body["data"]["name"] == "ReliefOps API"
