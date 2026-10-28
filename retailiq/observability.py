"""Privacy-minded structured event logs for the local Week 1 agent harness.

JSONL is rotated and bounded. Neither prompts nor response bodies are logged.
The UI endpoint exposes a strict allowlist, never exception stacks or secrets.
This complements LangSmith; it is NOT a substitute for remote LLM traces.
"""
from __future__ import annotations
from collections import deque
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timezone
import json
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import threading
import time
import traceback
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_LOG = ROOT / 'data' / 'logs' / 'retailiq.jsonl'
_REQUEST_ID: ContextVar[str | None] = ContextVar('retailiq_request_id', default=None)
_SESSION_ID: ContextVar[str | None] = ContextVar('retailiq_session_id', default=None)
_LOCK = threading.RLock()
_LOGGER = logging.getLogger('retailiq.events')
_LOGGER.setLevel(logging.INFO)
_LOGGER.propagate = False
_HANDLER_PATH: Path | None = None

# Strict allowlist prevents accidental prompt, credentials, URL, or response logging.
SAFE_FIELDS = frozenset({
    'agent', 'previous_agent', 'target_agent', 'intent', 'skill', 'tool',
    'status', 'status_code', 'method', 'path', 'duration_ms', 'route_fallback',
    'execution_mode', 'error_type', 'record_count', 'context_count',
    'subagent', 'input_tokens', 'output_tokens', 'model', 'session_id',
    'request_id', 'stack_trace',
})
UI_FIELDS = SAFE_FIELDS - {'stack_trace'}


def _log_path() -> Path:
    return Path(os.environ.get('RETAILIQ_LOG_FILE') or DEFAULT_LOG).expanduser().resolve()


class JsonEventFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        data = getattr(record, 'event_payload', {})
        return json.dumps(data, ensure_ascii=False, separators=(',', ':'))


def _logger() -> logging.Logger:
    global _HANDLER_PATH
    target = _log_path()
    with _LOCK:
        if _HANDLER_PATH != target or not _LOGGER.handlers:
            for handler in _LOGGER.handlers[:]:
                _LOGGER.removeHandler(handler)
                handler.close()
            target.parent.mkdir(parents=True, exist_ok=True)
            handler = RotatingFileHandler(target, maxBytes=2_000_000,
                                          backupCount=3, encoding='utf-8')
            handler.setFormatter(JsonEventFormatter())
            _LOGGER.addHandler(handler)
            _HANDLER_PATH = target
            # Local users only; make private when the platform supports chmod.
            try:
                os.chmod(target, 0o600)
            except OSError:
                pass
        return _LOGGER


def request_id() -> str:
    return _REQUEST_ID.get() or ''


@contextmanager
def bind_context(*, request: str | None = None, session: str | None = None):
    tokens = []
    if request is not None:
        tokens.append((_REQUEST_ID, _REQUEST_ID.set(request)))
    if session is not None:
        tokens.append((_SESSION_ID, _SESSION_ID.set(session)))
    try:
        yield
    finally:
        for var, token in reversed(tokens):
            var.reset(token)


def new_request_id() -> str:
    return uuid4().hex


def log_event(event: str, *, level: str = 'INFO', **fields) -> None:
    payload = {
        'timestamp': datetime.now(timezone.utc).isoformat(timespec='milliseconds'),
        'level': level if level in ('DEBUG', 'INFO', 'WARNING', 'ERROR') else 'INFO',
        'event': str(event)[:80],
    }
    if request_id():
        payload['request_id'] = request_id()
    if _SESSION_ID.get():
        payload['session_id'] = _SESSION_ID.get()
    for key, value in fields.items():
        if key not in SAFE_FIELDS or value is None:
            continue
        if key in ('request_id', 'session_id'):
            continue  # context IDs cannot be overridden via arbitrary caller fields
        if key == 'stack_trace':
            payload[key] = value[-15:] if isinstance(value, list) else []
        elif isinstance(value, (int, float, bool)):
            payload[key] = value
        elif isinstance(value, str):
            payload[key] = value[:160]
    _logger().log(getattr(logging, payload['level']), event, extra={'event_payload': payload})


def log_exception(event: str, error: BaseException, **fields) -> None:
    # Extract code locations only: never log exception messages or source lines,
    # which may contain prompts, credentials or provider response details.
    stack = [{'file': Path(frame.filename).name, 'line': frame.lineno,
              'function': frame.name[:80]}
             for frame in traceback.extract_tb(error.__traceback__)]
    log_event(event, level='ERROR', error_type=type(error).__name__,
              stack_trace=stack, **fields)


@contextmanager
def observed(event: str, **fields):
    start = time.perf_counter()
    log_event(event + '.started', status='started', **fields)
    try:
        yield
    except Exception as error:
        log_exception(event + '.failed', error, status='failed',
                      duration_ms=round((time.perf_counter() - start) * 1000, 2), **fields)
        raise
    else:
        log_event(event + '.completed', status='success',
                  duration_ms=round((time.perf_counter() - start) * 1000, 2), **fields)


def list_events(*, limit: int = 100, level: str | None = None,
                session_id: str | None = None, request_id: str | None = None) -> list[dict]:
    """Recent newest-first safe events, bounded by log rotation and result limit."""
    target = _log_path()
    paths = [target.with_name(target.name + f'.{i}') for i in (3, 2, 1)] + [target]
    # Loading at most 2 MB * 4 rotated files is acceptable for local demo.
    recent = deque(maxlen=2000)
    with _LOCK:
        for path in paths:
            if not path.exists():
                continue
            with path.open('r', encoding='utf-8', errors='replace') as file:
                for line in file:
                    try:
                        item = json.loads(line)
                    except (ValueError, TypeError):
                        continue
                    if item.get('event') and item.get('level'):
                        recent.append(item)
    matching = []
    for item in reversed(recent):
        if level and item.get('level') != level:
            continue
        if session_id and item.get('session_id') != session_id:
            continue
        if request_id and item.get('request_id') != request_id:
            continue
        matching.append({key: val for key, val in item.items()
                         if key in UI_FIELDS or key in ('timestamp', 'level', 'event')})
        if len(matching) >= min(max(limit, 1), 200):
            break
    return matching
