"""Local durable chat sessions; independent from the read-only retail analytics fixture.

Local demo only: no authentication or tenant isolation. Avoid putting API secrets in messages.
"""
from __future__ import annotations
import os
import json
from pathlib import Path
import sqlite3
import threading
from contextlib import contextmanager
from dataclasses import dataclass, field
from uuid import uuid4

DEFAULT_DB = Path(__file__).resolve().parents[2] / 'data' / 'chat_sessions.sqlite3'
MAX_SESSION_MESSAGES = 200  # Bounded API response; older messages stay in SQLite.
MAX_STORED_ANSWER_CHARS = 20_000  # Explicit guard against oversized model output.
MAX_STORED_EVIDENCE_CHARS = 100_000
MAX_TRACE_EVENTS = 160
MAX_STORED_TRACE_CHARS = 90_000


# Local single-process demo: prevent overlapping writes to the same conversation.
# Production multi-worker locking/authorization is deliberately deferred.
@dataclass
class _SessionGate:
    """Reference count prevents premature cleanup during competing requests."""
    lock: threading.Lock = field(default_factory=threading.Lock)
    references: int = 0


_SESSION_LOCKS: dict[str, _SessionGate] = {}
_LOCK_GUARD = threading.Lock()


class SessionBusyError(RuntimeError):
    """Another request is currently updating this conversation."""


@contextmanager
def session_mutation(session_id: str):
    """Serialize writes to a chat without retaining one lock per past session.

    The registry is single-process only (Week 1 local demo). The guard covers
    both admitted calls and a racing caller that must receive SessionBusyError.
    """
    with _LOCK_GUARD:
        gate = _SESSION_LOCKS.setdefault(session_id, _SessionGate())
        gate.references += 1
    acquired = False
    try:
        acquired = gate.lock.acquire(blocking=False)
        if not acquired:
            raise SessionBusyError('Session already processing a request')
        yield
    finally:
        if acquired:
            gate.lock.release()
        with _LOCK_GUARD:
            gate.references -= 1
            if gate.references == 0 and _SESSION_LOCKS.get(session_id) is gate:
                del _SESSION_LOCKS[session_id]



def _path() -> Path:
    return Path(os.getenv('RETAILIQ_CHAT_DB') or DEFAULT_DB)


@contextmanager
def _connect():
    path = _path()
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path, timeout=10)
    try:
        # Setup may throw (permission denied / invalid file / busy DB); it must
        # be inside finally too, or a connection can leak before first yield.
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
            content TEXT NOT NULL, intent TEXT, agent TEXT, evidence_json TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS ix_messages_session ON messages(session_id, id);
        CREATE TABLE IF NOT EXISTS execution_traces (
            session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
            request_id TEXT NOT NULL,
            events_json TEXT NOT NULL,
            truncated INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY(session_id,request_id)
        );
        ''')
        message_columns = {row['name'] for row in connection.execute('PRAGMA table_info(messages)')}
        if 'evidence_json' not in message_columns:
            connection.execute('ALTER TABLE messages ADD COLUMN evidence_json TEXT')
        if 'request_id' not in message_columns:
            connection.execute('ALTER TABLE messages ADD COLUMN request_id TEXT')
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
            # Pull the newest bounded window rather than allocating all messages
            # for a long-running session. Preserve ascending presentation order.
            rows = c.execute('''SELECT id, role, content, intent, agent, request_id, evidence_json, created_at
                FROM messages WHERE session_id=? ORDER BY id DESC LIMIT ?''',
                (sid, MAX_SESSION_MESSAGES + 1)).fetchall()
            result['messages_truncated'] = len(rows) > MAX_SESSION_MESSAGES
            result['messages'] = []
            for message in reversed(rows[:MAX_SESSION_MESSAGES]):
                item = dict(message)
                raw = item.pop('evidence_json', None)
                item['evidence'] = json.loads(raw) if raw else None
                result['messages'].append(item)
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
        if len(question) > 500:
            raise ValueError('Question is too long for a single chat turn')
        answer = str(response['answer'])
        if len(answer) > MAX_STORED_ANSWER_CHARS:
            raise ValueError('Assistant answer exceeds the persistence limit')
        agent = str(response.get('active_agent') or response.get('agent') or '')[:64]
        intent = str(response.get('intent') or '')[:32]
        records = response.get('records') or []
        contexts = response.get('contexts') or []
        evidence = {'intent': intent, 'as_of': response.get('as_of'),
                    'records': records[:200] if isinstance(records, list) else [],
                    'contexts': [{'source': str(item['source'])[:300]} for item in contexts[:100]
                                 if isinstance(item, dict) and isinstance(item.get('source'), str)]
                    if isinstance(contexts, list) else []}
        evidence_json = json.dumps(evidence, ensure_ascii=False)
        if len(evidence_json) > MAX_STORED_EVIDENCE_CHARS:
            evidence_json = json.dumps({'intent': intent, 'as_of': response.get('as_of'),
                                        'records': [], 'contexts': []})
        c.execute('INSERT INTO messages (session_id, role, content) VALUES (?, ?, ?)', (sid, 'user', question))
        c.execute('''INSERT INTO messages (session_id, role, content, intent, agent, evidence_json, request_id)
                     VALUES (?, ?, ?, ?, ?, ?, ?)''', (sid, 'assistant', answer, intent, agent,
                     evidence_json, response.get('request_id') or None))
        title = question.strip()[:80] if row['title'] == 'New conversation' else row['title']
        c.execute('''UPDATE sessions SET title=?,active_agent=?,updated_at=CURRENT_TIMESTAMP
                     WHERE id=?''', (title, agent, sid))


def delete_session(sid: str) -> bool:
    with _connect() as c:
        return c.execute('DELETE FROM sessions WHERE id=?', (sid,)).rowcount > 0


# Metadata-only, bounded execution traces. No prompts, answers, SQL, tokens or
# raw tool output. These are collected from the already redacted SSE event sink.
_TRACE_FIELDS = frozenset({
    'timestamp', 'event', 'level', 'request_id', 'session_id',
    'agent', 'previous_agent', 'target_agent', 'intent', 'skill', 'tool',
    'status', 'duration_ms', 'route_fallback', 'execution_mode',
    'error_type', 'subagent', 'mcp_server'
})


def save_execution_trace(sid: str, rid: str, events: list[dict]) -> bool:
    """Persist only events associated with an actual saved assistant turn.

    Ignore a late trace after deletion, a mismatched request, and any event
    fields that are not explicitly allowlisted.
    """
    if not sid or not rid or len(rid) > 64:
        return False
    safe = []
    truncated = len(events) > MAX_TRACE_EVENTS
    for raw in events[:MAX_TRACE_EVENTS]:
        if not isinstance(raw, dict) or raw.get('request_id') != rid or raw.get('session_id') != sid:
            continue
        item = {key: value for key, value in raw.items() if key in _TRACE_FIELDS
                and (isinstance(value, (str, int, float, bool)) and not
                     isinstance(value, complex))}
        if not isinstance(item.get('event'), str):
            continue
        safe.append(item)
    payload = json.dumps(safe, ensure_ascii=False, separators=(',', ':'), allow_nan=False)
    if len(payload) > MAX_STORED_TRACE_CHARS:
        truncated = True
        # Preserve prefix and include no partial serialized JSON.
        while safe and len(payload) > MAX_STORED_TRACE_CHARS:
            safe.pop()
            payload = json.dumps(safe, ensure_ascii=False, separators=(',', ':'), allow_nan=False)
    with _connect() as c:
        exists = c.execute('''SELECT 1 FROM messages
            WHERE session_id=? AND role='assistant' AND request_id=? LIMIT 1''',
            (sid, rid)).fetchone()
        if not exists:
            return False
        c.execute('''INSERT INTO execution_traces (session_id,request_id,events_json,truncated)
                     VALUES (?,?,?,?) ON CONFLICT(session_id,request_id)
                     DO UPDATE SET events_json=excluded.events_json,truncated=excluded.truncated''',
                  (sid, rid, payload, int(truncated)))
    return True


def get_execution_trace(sid: str, rid: str) -> dict | None:
    """None means absent/legacy, not a synthetic empty execution."""
    with _connect() as c:
        row = c.execute('''SELECT t.events_json,t.truncated
            FROM execution_traces t
            JOIN messages m ON m.session_id=t.session_id AND m.request_id=t.request_id
            WHERE t.session_id=? AND t.request_id=? AND m.role='assistant' LIMIT 1''',
            (sid, rid)).fetchone()
        if not row:
            return None
        return {'request_id': rid, 'events': json.loads(row['events_json']),
                'truncated': bool(row['truncated']), 'status': 'complete'}
