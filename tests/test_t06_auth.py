"""T06 Task 1: real local authentication boundary, no authentication bypass."""
from __future__ import annotations

import sqlite3

import pytest
from fastapi.testclient import TestClient

from retailiq.api.http import app
from retailiq.infrastructure import auth


ORIGIN = {"Origin": "http://testserver"}
PASSWORD = "correct horse battery staple! 2026"


@pytest.fixture
def api(tmp_path, monkeypatch):
    monkeypatch.setenv("RETAILIQ_CHAT_DB", str(tmp_path / "t06_app.sqlite"))
    with TestClient(app) as client:
        yield client


def _create_user(username="analyst01", role="analyst"):
    return auth.create_local_user(username, role, PASSWORD)


def _login(api, username="analyst01", password=PASSWORD, headers=None):
    return api.post(
        "/api/auth/login", json={"username": username, "password": password},
        headers=ORIGIN if headers is None else headers,
    )


def test_cli_user_hash_not_plaintext(api):
    uid = _create_user()
    assert uid
    with sqlite3.connect(auth._path()) as db:
        row = db.execute(
            "SELECT password_hash, role FROM users WHERE id=?", (uid,)
        ).fetchone()
    assert row[0].startswith("$argon2id$")
    assert PASSWORD not in row[0]
    assert row[1] == "analyst"


def test_invalid_login_returns_generic_401_and_throttles(api):
    _create_user()
    missing = _login(api, "unknown_user", "bad password")
    assert missing.status_code == 401
    assert "user" not in missing.json()["detail"].lower()
    for _ in range(5):
        bad = _login(api, password="bad password")
        assert bad.status_code == 401
        assert bad.json() == missing.json()
    # Correct password is locked out for this username/IP bucket.
    assert _login(api).status_code == 401


def test_cookie_me_logout_revocation_and_disabled_user(api):
    uid = _create_user()
    response = _login(api)
    assert response.status_code == 200, response.text
    cookie = response.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=strict" in cookie
    assert "path=/" in cookie and "domain=" not in cookie
    assert "retailiq_session" not in response.json()
    me = api.get("/api/auth/me")
    assert me.status_code == 200
    assert me.json()["user_id"] == uid
    assert me.json()["role"] == "analyst"
    csrf = me.json()["csrf_token"]
    assert csrf and "no-store" in me.headers.get("cache-control", "")
    logout = api.post("/api/auth/logout", headers={**ORIGIN, "X-CSRF-Token": csrf})
    assert logout.status_code == 200
    assert api.get("/api/auth/me").status_code == 401
    with sqlite3.connect(auth._path()) as db:
        db.execute("UPDATE users SET disabled=1 WHERE id=?", (uid,))
        db.commit()
    assert _login(api).status_code == 401


def test_csrf_mismatch_and_origin_required(api):
    _create_user()
    assert _login(api, headers={}).status_code == 403
    assert _login(api, headers={"Origin": "http://evil.example"}).status_code == 403
    assert _login(api).status_code == 200
    assert api.post("/api/auth/logout", headers=ORIGIN).status_code == 403
    assert api.post("/api/auth/logout", headers={**ORIGIN, "X-CSRF-Token": "not-token"}).status_code == 403
    assert api.post("/api/auth/logout", headers={"X-CSRF-Token": api.get("/api/auth/me").json()["csrf_token"]}).status_code == 403
    assert api.get("/api/auth/me").status_code == 200


def test_unauthenticated_ask_fails_before_model_call(api, monkeypatch):
    import retailiq.api.http as http

    calls = []
    monkeypatch.setattr(http, "ask", lambda question, **kwargs: calls.append(question) or {"answer": "unsafe"})
    assert api.post("/ask", json={"question": "List top sellers"}, headers=ORIGIN).status_code == 401
    assert api.post("/ask/stream", json={"question": "List top sellers"}, headers=ORIGIN).status_code == 401
    assert api.get("/api/sessions").status_code == 401
    assert api.get("/api/logs").status_code == 401
    assert calls == []


def test_authenticated_ask_requires_valid_csrf(api, monkeypatch):
    import retailiq.api.http as http

    _create_user()
    assert _login(api).status_code == 200
    assert api.post("/ask", json={"question": "List top sellers"}, headers=ORIGIN).status_code == 403
    calls = []
    monkeypatch.setattr(http, "ask", lambda question, **kwargs:
                        calls.append(question) or {"answer": "trusted", "records": [], "contexts": []})
    csrf = api.get("/api/auth/me").json()["csrf_token"]
    ok = api.post("/ask", json={"question": "List top sellers"},
                  headers={**ORIGIN, "X-CSRF-Token": csrf})
    assert ok.status_code == 200, ok.text
    assert ok.json()["answer"] == "trusted"
    assert calls == ["List top sellers"]


def test_authenticated_owned_sessions_open_but_global_logs_remain_closed(api):
    _create_user()
    assert _login(api).status_code == 200
    owned = api.get("/api/sessions")
    assert owned.status_code == 200
    assert owned.json() == {"sessions": []}
    assert api.get("/api/logs").status_code == 403
