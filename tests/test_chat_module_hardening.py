"""Chat & Sessions hardening: bounded resources, concurrency, security and cleanup."""
import threading
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from retailiq.api import app
from retailiq.api import http
from retailiq.infrastructure import sessions


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv('RETAILIQ_MODE', 'offline')
    monkeypatch.setenv('RETAILIQ_CHAT_DB', str(tmp_path / 'sessions.sqlite3'))
    monkeypatch.setenv('RETAILIQ_LOG_FILE', str(tmp_path / 'events.jsonl'))
    return TestClient(app)


def test_registry_releases_all_idle_gates_even_after_exceptions():
    before = set(sessions._SESSION_LOCKS)
    for i in range(200):
        with sessions.session_mutation('new-session-' + str(i)):
            assert sessions._SESSION_LOCKS['new-session-' + str(i)].references == 1
    assert set(sessions._SESSION_LOCKS) == before
    with pytest.raises(ValueError, match='purposeful'):
        with sessions.session_mutation('fails-after-lock'):
            raise ValueError('purposeful')
    assert 'fails-after-lock' not in sessions._SESSION_LOCKS


def test_competing_call_gets_session_busy_and_keeps_active_gate():
    sid = 'same-session-race'
    entered = threading.Event()
    release = threading.Event()

    def holder():
        with sessions.session_mutation(sid):
            entered.set()
            assert release.wait(timeout=5)

    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(holder)
        assert entered.wait(timeout=2)
        with pytest.raises(sessions.SessionBusyError):
            with sessions.session_mutation(sid):
                pytest.fail('The concurrent mutation must not start')
        assert sessions._SESSION_LOCKS[sid].references == 1
        release.set()
        future.result(timeout=5)
    assert sid not in sessions._SESSION_LOCKS


def test_other_session_not_blocked_during_mutation():
    with sessions.session_mutation('chat-a'):
        with sessions.session_mutation('chat-b'):
            pass
    assert 'chat-a' not in sessions._SESSION_LOCKS
    assert 'chat-b' not in sessions._SESSION_LOCKS


def test_sse_capacity_rejection_is_fast_and_does_not_spawn_worker(client, monkeypatch):
    semaphore = threading.BoundedSemaphore(value=1)
    assert semaphore.acquire(blocking=False)
    monkeypatch.setattr(http, '_STREAM_WORKER_SLOTS', semaphore)
    try:
        response = client.post('/ask/stream', json={
            'question': 'Which products are top sellers?'})
        assert response.status_code == 503
        assert response.json()['detail'].startswith('Chat streaming capacity reached')
        assert response.headers['retry-after'] == '1'
    finally:
        semaphore.release()


def test_sse_worker_frees_slot_even_if_stream_body_is_not_consumed(monkeypatch, tmp_path):
    monkeypatch.setenv('RETAILIQ_MODE', 'offline')
    monkeypatch.setenv('RETAILIQ_LOG_FILE', str(tmp_path / 'events.jsonl'))
    semaphore = threading.BoundedSemaphore(value=1)
    monkeypatch.setattr(http, '_STREAM_WORKER_SLOTS', semaphore)
    entered = threading.Event()
    allowed = threading.Event()

    def slow_ask(*args, **kwargs):
        entered.set()
        assert allowed.wait(timeout=5)
        return {'answer': 'OK', 'records': [], 'contexts': []}

    monkeypatch.setattr(http, 'ask', slow_ask)
    response = http.stream_answer(http.AskBody(question='Get the inventory report'),
                                  SimpleNamespace(state=SimpleNamespace(request_id='test-slot')))
    try:
        assert entered.wait(timeout=2)
        assert not semaphore.acquire(blocking=False)
    finally:
        allowed.set()
    assert semaphore.acquire(timeout=3), 'A completed worker must free its slot'
    semaphore.release()
    # Constructing the response itself must not be required for cleanup.
    assert response.media_type == 'text/event-stream'


def test_local_only_guard_rejects_untrusted_host(client):
    allowed = client.get('/health')
    assert allowed.status_code == 200
    rejected = client.get('/api/sessions', headers={'host': 'outside.example'})
    assert rejected.status_code == 403
    assert 'local-only' in rejected.json()['detail']
    assert client.get('/assets/agent-identity.js', headers={'host': 'outside.example'}).status_code == 403
    assert client.get('/api/sessions', headers={'host': 'localhost:8000'}).status_code == 200


def test_long_session_returns_bounded_latest_history_in_order(client):
    sid = client.post('/api/sessions', json={}).json()['id']
    db = sessions._path()
    with sqlite3.connect(db) as connection:
        connection.executemany(
            'INSERT INTO messages (session_id,role,content) VALUES (?,?,?)',
            [(sid, 'user', f'message-{i}') for i in range(260)]
        )
    snapshot = client.get(f'/api/sessions/{sid}').json()
    messages = snapshot['messages']
    assert snapshot['messages_truncated'] is True
    assert len(messages) == sessions.MAX_SESSION_MESSAGES
    assert messages[0]['content'] == 'message-60'
    assert messages[-1]['content'] == 'message-259'
    # Data is retained in SQLite even when the API response is bounded.
    with sqlite3.connect(db) as connection:
        count = connection.execute('SELECT COUNT(*) FROM messages WHERE session_id=?', (sid,)).fetchone()[0]
    assert count == 260


def test_oversized_answer_rejected_atomically(client):
    sid = client.post('/api/sessions', json={}).json()['id']
    with pytest.raises(ValueError, match='persistence limit'):
        sessions.add_turn(sid, 'A valid business question', {
            'answer': 'x' * (sessions.MAX_STORED_ANSWER_CHARS + 1),
            'active_agent': 'sales_agent'
        })
    assert client.get(f'/api/sessions/{sid}').json()['messages'] == []
    with pytest.raises(ValueError, match='too long'):
        sessions.add_turn(sid, 'q' * 501, {'answer': 'OK'})
    assert client.get(f'/api/sessions/{sid}').json()['messages'] == []


def test_sqlite_connection_is_closed_when_initialization_raises(tmp_path, monkeypatch):
    monkeypatch.setenv('RETAILIQ_CHAT_DB', str(tmp_path / 'broken.sqlite3'))
    closed = []

    class BrokenConnection:
        row_factory = None

        def execute(self, _sql):
            raise sqlite3.OperationalError('failed while initializing PRAGMA')

        def close(self):
            closed.append(True)

    monkeypatch.setattr(sessions.sqlite3, 'connect',
                        lambda *args, **kwargs: BrokenConnection())
    with pytest.raises(sqlite3.OperationalError, match='initializing'):
        with sessions._connect():
            pytest.fail('Initialization must not succeed')
    assert closed == [True]


def test_chat_ui_discloses_history_window_limit(client):
    html = client.get('/').text
    js = client.get('/assets/app.js').text
    assert 'id="chat-history-limit"' in html
    assert 'Showing the 200 most recent messages' in html
    assert "session.messages_truncated !== true" in js
