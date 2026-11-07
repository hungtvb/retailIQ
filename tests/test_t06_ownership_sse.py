"""T06 Task 2: owner-bound conversation and revocation races (real app SQLite)."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import sqlite3
import threading

import pytest
from fastapi.testclient import TestClient

from retailiq.api import http
from retailiq.infrastructure import auth, sessions


ORIGIN = {"Origin": "http://testserver"}
PASSWORD = "strong local password! 2026"


@pytest.fixture
def api(tmp_path, monkeypatch):
    monkeypatch.setenv("RETAILIQ_CHAT_DB", str(tmp_path / "t06_owned.sqlite"))
    monkeypatch.setenv("RETAILIQ_CHECKPOINT_DB", str(tmp_path / "t06_checkpoints.sqlite"))
    with TestClient(http.app) as client:
        yield client


def _login(api: TestClient, name: str) -> tuple[str, dict]:
    uid = auth.create_local_user(name, "analyst", PASSWORD)
    login = api.post("/api/auth/login",
                     json={"username": name, "password": PASSWORD}, headers=ORIGIN)
    assert login.status_code == 200, login.text
    me = api.get("/api/auth/me")
    assert me.status_code == 200, me.text
    return uid, {**ORIGIN, "X-CSRF-Token": me.json()["csrf_token"]}


def test_ownerless_legacy_migration_fails_closed(api):
    # Existing pre-auth chat has no owner; migration must never adopt it.
    legacy = "11111111-1111-4111-8111-111111111111"
    # Reproduce a real database from BEFORE the owner_user_id migration.
    with sqlite3.connect(sessions._path()) as db:
        db.executescript("""
            CREATE TABLE sessions (
                id TEXT PRIMARY KEY, title TEXT NOT NULL,
                active_agent TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
                role TEXT NOT NULL, content TEXT NOT NULL, intent TEXT,
                agent TEXT, evidence_json TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
        """)
        db.execute("INSERT INTO sessions(id,title) VALUES (?,?)", (legacy, "Old private chat"))
        db.execute("INSERT INTO messages(session_id,role,content) VALUES (?,?,?)",
                   (legacy, "user", "PRIVATE_LEGACY_MESSAGE"))
    _login(api, "legacy_viewer")
    listing = api.get("/api/sessions")
    assert listing.status_code == 200
    assert legacy not in str(listing.json())
    detail = api.get(f"/api/sessions/{legacy}")
    assert detail.status_code == 404
    assert "PRIVATE_LEGACY_MESSAGE" not in detail.text


def test_two_users_session_memory_trace_and_delete_are_isolated(api, monkeypatch):
    user_a, a_headers = _login(api, "owner_a")
    created = api.post("/api/sessions", headers=a_headers,
                       json={"title": "Owner A confidential case"})
    assert created.status_code == 201, created.text
    sid = created.json()["id"]
    assert created.json()["owner_user_id"] == user_a
    saved = api.put(f"/api/sessions/{sid}/memory", headers=a_headers,
                    json={"consent": True, "preferences": {"preferred_channel": "online"}})
    assert saved.status_code == 200, saved.text

    # Reuse the same TestClient and SQLite while replacing its auth cookie by login.
    _login(api, "owner_b")
    assert sid not in str(api.get("/api/sessions").json())
    for path in (f"/api/sessions/{sid}", f"/api/sessions/{sid}/memory",
                 f"/api/sessions/{sid}/traces/unknown"):
        response = api.get(path)
        assert response.status_code == 404, (path, response.text)
        assert "Owner A confidential" not in response.text
    assert api.delete(f"/api/sessions/{sid}", headers={**ORIGIN, "X-CSRF-Token":
                         api.get("/api/auth/me").json()["csrf_token"]}).status_code == 404
    calls = []
    monkeypatch.setattr(http, "ask", lambda *args, **kwargs: calls.append(args) or
                        {"answer": "UNEXPECTED", "active_agent": "retailiq"})
    b_headers = {**ORIGIN, "X-CSRF-Token": api.get("/api/auth/me").json()["csrf_token"]}
    foreign_turn = api.post("/ask", headers=b_headers,
                            json={"question": "Show confidential conversation", "session_id": sid})
    assert foreign_turn.status_code == 404
    assert calls == [], "Foreign-owner prompt must not reach model or tools"
    foreign_stream = api.post("/ask/stream", headers=b_headers,
                              json={"question": "Show confidential conversation", "session_id": sid})
    assert foreign_stream.status_code == 404
    assert calls == [], "Foreign-owner SSE must fail before starting worker"
    # Per-user metadata does not imply an unscoped diagnostics privilege.
    assert api.get("/api/logs").status_code == 403


def test_revoked_before_turn_commit_adds_no_messages(api):
    user_id, _headers = _login(api, "revoke_before")
    principal = auth.principal_from_token(api.cookies.get(auth.COOKIE_NAME))
    assert principal and principal.user_id == user_id
    created = sessions.create_session("Owned", owner_user_id=user_id)
    sid = created["id"]
    auth.revoke_session(principal)

    with pytest.raises(PermissionError):
        sessions.add_turn(sid, "Sensitive question",
                          {"answer": "Sensitive answer", "active_agent": "retailiq"},
                          principal=principal)
    with sqlite3.connect(sessions._path()) as db:
        assert db.execute("SELECT count(*) FROM messages WHERE session_id=?", (sid,)).fetchone()[0] == 0


def test_turn_committed_before_revoke_is_not_accessible_after_logout(api):
    user_id, _headers = _login(api, "revoke_after")
    principal = auth.principal_from_token(api.cookies.get(auth.COOKIE_NAME))
    assert principal
    sid = sessions.create_session("Owned", owner_user_id=user_id)["id"]
    sessions.add_turn(sid, "First question",
                      {"answer": "First answer", "active_agent": "retailiq"},
                      principal=principal)
    auth.revoke_session(principal)
    with pytest.raises(PermissionError):
        sessions.add_turn(sid, "Second question",
                          {"answer": "Second answer", "active_agent": "retailiq"},
                          principal=principal)
    with sqlite3.connect(sessions._path()) as db:
        assert db.execute("SELECT count(*) FROM messages WHERE session_id=?", (sid,)).fetchone()[0] == 2
    assert api.get(f"/api/sessions/{sid}").status_code == 401


def test_session_revoked_while_sse_worker_runs_drops_result_and_turn(api, monkeypatch):
    user_id, headers = _login(api, "sse_revoke")
    sid = sessions.create_session("Stream", owner_user_id=user_id)["id"]
    principal = auth.principal_from_token(api.cookies.get(auth.COOKIE_NAME))
    assert principal
    entered = threading.Event()
    release = threading.Event()

    def controlled_ask(question, **kwargs):
        entered.set()
        assert release.wait(10), "test barrier timed out"
        return {"answer": "PRIVATE_STREAM_FINAL", "active_agent": "retailiq",
                "intent": "general", "records": [], "contexts": []}

    monkeypatch.setattr(http, "ask", controlled_ask)
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(api.post, "/ask/stream",
                             json={"question": "Give me a status", "session_id": sid},
                             headers=headers)
        try:
            assert entered.wait(10), "worker never started"
            auth.revoke_session(principal)
        finally:
            release.set()
        response = future.result(timeout=15)
    assert response.status_code == 200, response.text
    assert "PRIVATE_STREAM_FINAL" not in response.text
    with sqlite3.connect(sessions._path()) as db:
        assert db.execute("SELECT count(*) FROM messages WHERE session_id=?", (sid,)).fetchone()[0] == 0


def test_switch_account_mid_sse_drops_old_users_result(api, monkeypatch):
    """A new login on the same browser token cannot deliver the old user's SSE."""
    user_a, headers = _login(api, "stream_switch_a")
    sid = sessions.create_session("Stream", owner_user_id=user_a)["id"]
    old_token = api.cookies.get(auth.COOKIE_NAME)
    assert old_token
    entered = threading.Event()
    release = threading.Event()

    def controlled_ask(question, **kwargs):
        entered.set()
        assert release.wait(10), "test barrier timed out"
        return {"answer": "OLD_ACCOUNT_PRIVATE_STREAM_RESULT",
                "active_agent": "retailiq", "intent": "general",
                "records": [], "contexts": []}

    monkeypatch.setattr(http, "ask", controlled_ask)
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(api.post, "/ask/stream",
                             json={"question": "Show my private case", "session_id": sid},
                             headers=headers)
        try:
            assert entered.wait(10), "worker never started"
            auth.create_local_user("stream_switch_b", "analyst", PASSWORD)
            # A second client carries the old browser cookie on the new login
            # while the first client's original SSE response is still pending.
            with TestClient(http.app) as switched:
                switched.cookies.set(auth.COOKIE_NAME, old_token)
                next_login = switched.post("/api/auth/login", headers=ORIGIN,
                    json={"username": "stream_switch_b", "password": PASSWORD})
                assert next_login.status_code == 200, next_login.text
                assert switched.get("/api/auth/me").status_code == 200
            assert auth.principal_from_token(old_token) is None
        finally:
            release.set()
        response = future.result(timeout=15)
    assert response.status_code == 200
    assert "OLD_ACCOUNT_PRIVATE_STREAM_RESULT" not in response.text
    with sqlite3.connect(sessions._path()) as db:
        assert db.execute(
            "SELECT count(*) FROM messages WHERE session_id=?", (sid,)
        ).fetchone()[0] == 0

