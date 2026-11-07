"""Reusable real-login test client. Never mocks or bypasses authentication."""
from __future__ import annotations

from uuid import uuid4
from fastapi.testclient import TestClient
from retailiq.infrastructure import auth

TEST_PASSWORD = "temporary controlled test credential 2026!"
TEST_ORIGIN = "http://testserver"


def signed_in_client(app, *, client: TestClient | None = None, role: str = "analyst") -> TestClient:
    """Provision isolated synthetic account, log in through actual HTTP, set CSRF."""
    client = client if client is not None else TestClient(app)
    username = "case_" + uuid4().hex[:20]
    auth.create_local_user(username, role, TEST_PASSWORD)
    response = client.post("/api/auth/login", headers={"Origin": TEST_ORIGIN},
                           json={"username": username, "password": TEST_PASSWORD})
    assert response.status_code == 200, response.text
    me = client.get("/api/auth/me")
    assert me.status_code == 200, me.text
    client.headers.update({"Origin": TEST_ORIGIN, "X-CSRF-Token": me.json()["csrf_token"]})
    return client


def active_principal(client: TestClient):
    principal = auth.principal_from_token(client.cookies.get(auth.COOKIE_NAME))
    assert principal is not None
    return principal
