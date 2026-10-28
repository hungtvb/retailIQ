"""Local durable chat sessions; independent from the read-only retail analytics fixture.

Local demo only: no authentication or tenant isolation. Avoid putting API secrets in messages.
"""
from __future__ import annotations
import os
from pathlib import Path
import sqlite3
import threading
from contextlib import contextmanager
from uuid import uuid4

DEFAULT_DB = Path(__file__).resolve().parents[2] / 'data' / 'chat_sessions.sqlite3'

# Local single-process demo: prevent overlapping writes to the same conversation.
# Production multi-worker locking/authorization is deliberately deferred.
_SESSION_LOCKS: dict[str, threading.Lock] = {}
_LOCK_GUARD = threading.Lock()


class SessionBusyError(RuntimeError):
    """Another request is currently updating this conversation."""


@contextmanager
def session_mutation(session_id: str):
    with _LOCK_GUARD:
        lock = _SESSION_LOCKS.setdefault(session_id, threading.Lock())
    if not lock.acquire(blocking=False):
        raise SessionBusyError('Session already processing a request')
    try:
        yield
    finally:
        lock.release()



def _path() -> Path:
    return Path(os.getenv('RETAILIQ_CHAT_DB') or DEFAULT_DB)


@contextmanager
def _connect():
    path = _path()
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path, timeout=10)
    connection.row_factory = sqlite3.Row
    connection.execute('PRAGMA foreign_keys = ON')
    connection.execute('PRAGMA busy_timeout = 10000')
    connection.executescript('''
    CREATE TABLE IF NOT EXISTS sessions (
        id TEXT PRIMARY KEY, title TEXT NOT NULL DEFAULT 'New conversation',
        active_agent TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
        role TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
        content TEXT NOT NULL, intent TEXT, agent TEXT,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    );
    CREATE INDEX IF NOT EXISTS ix_messages_session ON messages(session_id, id);
    ''')
    try:
        with connection:
            yield connection
    finally:
        connection.close()


def create_session(title: str = 'New conversation') -> dict:
    sid = str(uuid4())
    title = title.strip()[:80] or 'New conversation'
    with _connect() as c:
        c.execute('INSERT INTO sessions (id, title) VALUES (?,?)', (sid, title))
    return get_session(sid, include_messages=False)


def get_session(sid: str, *, include_messages: bool = True) -> dict | None:
    with _connect() as c:
        row = c.execute('SELECT * FROM sessions WHERE id=?', (sid,)).fetchone()
        if row is None:
            return None
        result = dict(row)
        if include_messages:
            result['messages'] = [dict(m) for m in c.execute(
                'SELECT id, role, content, intent, agent, created_at FROM messages WHERE session_id=? ORDER BY id', (sid,)
            )]
        return result


def list_sessions(limit: int = 50) -> list[dict]:
    with _connect() as c:
        return [dict(r) for r in c.execute('''
            SELECT s.*, (SELECT COUNT(*) FROM messages m WHERE m.session_id=s.id) AS message_count
            FROM sessions s ORDER BY s.updated_at DESC, s.rowid DESC LIMIT ?
        ''', (min(max(limit, 1), 100),))]


def history(sid: str, limit: int = 12) -> list[dict]:
    with _connect() as c:
        if not c.execute('SELECT 1 FROM sessions WHERE id=?', (sid,)).fetchone():
            raise KeyError('Unknown session')
        rows = c.execute('''SELECT role, content, intent, agent FROM messages
            WHERE session_id=? ORDER BY id DESC LIMIT ?''', (sid, min(max(limit, 1), 30))).fetchall()
        return [dict(r) for r in reversed(rows)]


def add_turn(sid: str, question: str, response: dict) -> None:
    """Atomic pair of messages; only called after successful execution."""
    with _connect() as c:
        row = c.execute('SELECT title FROM sessions WHERE id=?', (sid,)).fetchone()
        if row is None:
            raise KeyError('Unknown session')
        answer = str(response['answer'])
        agent = str(response.get('active_agent') or response.get('agent') or '')[:64]
        intent = str(response.get('intent') or '')[:32]
        c.execute('INSERT INTO messages (session_id, role, content) VALUES (?, ?, ?)', (sid, 'user', question))
        c.execute('''INSERT INTO messages (session_id, role, content, intent, agent)
                     VALUES (?, ?, ?, ?, ?)''', (sid, 'assistant', answer, intent, agent))
        title = question.strip()[:80] if row['title'] == 'New conversation' else row['title']
        c.execute('''UPDATE sessions SET title=?,active_agent=?,updated_at=CURRENT_TIMESTAMP
                     WHERE id=?''', (title, agent, sid))


def delete_session(sid: str) -> bool:
    with _connect() as c:
        return c.execute('DELETE FROM sessions WHERE id=?', (sid,)).rowcount > 0
