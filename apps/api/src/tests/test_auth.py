"""Auth-foundation tests — verify the get_current_user dependency 401s correctly."""
from fastapi.testclient import TestClient

from src.main import app

client = TestClient(app)


def test_shipments_requires_auth() -> None:
    """Unauthenticated request to a protected route must 401 with our envelope."""
    response = client.get("/api/shipments")
    assert response.status_code == 401
    body = response.json()
    assert body["data"] is None
    assert body["error"]["code"] == "AUTH_MISSING"


def test_shipments_rejects_malformed_bearer() -> None:
    response = client.get(
        "/api/shipments", headers={"Authorization": "Token abc.def.ghi"}
    )
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "AUTH_MALFORMED"


def test_shipments_rejects_invalid_token() -> None:
    response = client.get(
        "/api/shipments", headers={"Authorization": "Bearer not-a-real-token"}
    )
    # Either AUTH_INVALID or AUTH_EXPIRED — both are 401.
    assert response.status_code == 401
    assert response.json()["error"]["code"] in {"AUTH_INVALID", "AUTH_EXPIRED"}


def test_me_requires_auth() -> None:
    response = client.get("/api/auth/me")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "AUTH_MISSING"


def test_set_role_requires_auth() -> None:
    response = client.post(
        "/api/auth/set-role",
        json={"uid": "any", "role": "volunteer", "orgId": "any"},
    )
    assert response.status_code == 401
