"""Local, bounded and privacy-preserving application telemetry.

Best-effort instrumentation cannot fail a business request. JSONL is local
and rotated; its viewer exposes only sanitized, allowlisted scalar metadata.
Not a substitute for provider traces or reliable distributed telemetry.
"""
from __future__ import annotations

from collections import deque
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timezone
import json
import logging
from logging.handlers import RotatingFileHandler
import math
import os
from pathlib import Path
import re
import threading
import time
import traceback
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_LOG = ROOT / 'data' / 'logs' / 'retailiq.jsonl'
_REQUEST_ID: ContextVar[str | None] = ContextVar('retailiq_request_id', default=None)
_SESSION_ID: ContextVar[str | None] = ContextVar('retailiq_session_id', default=None)
_EVENT_SINK: ContextVar[object | None] = ContextVar('retailiq_event_sink', default=None)
_LOCK = threading.RLock()
_LOGGER = logging.getLogger('retailiq.events')
_LOGGER.setLevel(logging.INFO)
_LOGGER.propagate = False
_HANDLER_PATH: Path | None = None
_WRITE_FAILURES = 0
_LAST_ERROR_TYPE: str | None = None
_LOG_AVAILABLE = True
_MAX_LOG_LINE_BYTES = 8192

SAFE_FIELDS = frozenset({
    'agent', 'previous_agent', 'target_agent', 'intent', 'skill', 'tool',
    'status', 'status_code', 'method', 'path', 'duration_ms', 'route_fallback',
    'execution_mode', 'error_type', 'record_count', 'context_count',
    'subagent', 'input_tokens', 'output_tokens',
    'session_id', 'request_id', 'stack_trace',
})
UI_FIELDS = SAFE_FIELDS - {'stack_trace'}
_EVENT_RE = re.compile(r'^[a-z][a-z0-9_.-]{0,79}$')
_FIELD_RE = re.compile(r'^[A-Za-z0-9_./:{}-]{1,160}$')
_SENSITIVE_RE = re.compile(
    r'(?:sk-[A-Za-z0-9]|bearer|api[_-]?key|secret|password|token)', re.I)
_TIMESTAMP_RE = re.compile(r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}[.\d]*\+00:00$')


def _log_path() -> Path:
    return Path(os.environ.get('RETAILIQ_LOG_FILE') or DEFAULT_LOG).expanduser().resolve()


def _mark_log_failure(error: BaseException) -> None:
    global _WRITE_FAILURES, _LAST_ERROR_TYPE, _LOG_AVAILABLE
    with _LOCK:
        _WRITE_FAILURES += 1
        _LAST_ERROR_TYPE = type(error).__name__
        _LOG_AVAILABLE = False


def log_health() -> dict:
    """Diagnostic counters only; no credentials or exception messages."""
    with _LOCK:
        return {'available': _LOG_AVAILABLE, 'write_failures': _WRITE_FAILURES,
                'last_error_type': _LAST_ERROR_TYPE}


class SafeRotatingFileHandler(RotatingFileHandler):
    def handleError(self, record: logging.LogRecord) -> None:
        # Standard handleError can print a traceback and original event to
        # stderr. Neither are appropriate for potentially private log events.
        import sys
        error = sys.exc_info()[1]
        _mark_log_failure(error if error is not None else OSError())


class JsonEventFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        return json.dumps(record.event_payload, ensure_ascii=False,
                          allow_nan=False, separators=(',', ':'))


def _logger() -> logging.Logger:
    global _HANDLER_PATH
    target = _log_path()
    with _LOCK:
        if _HANDLER_PATH != target or not _LOGGER.handlers:
            # Prepare new sink before releasing the previous one. A failed
            # setup must not leave an unnecessary reference to a new handler.
            target.parent.mkdir(parents=True, exist_ok=True)
            handler = SafeRotatingFileHandler(target, maxBytes=2_000_000,
                                              backupCount=3, encoding='utf-8')
            handler.setFormatter(JsonEventFormatter())
            for old in _LOGGER.handlers[:]:
                _LOGGER.removeHandler(old)
                old.close()
            _LOGGER.addHandler(handler)
            _HANDLER_PATH = target
            try:
                os.chmod(target, 0o600)
            except OSError:
                pass
        return _LOGGER


def request_id() -> str:
    return _REQUEST_ID.get() or ''


def session_id() -> str:
    return _SESSION_ID.get() or ''


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


@contextmanager
def bind_event_sink(callback):
    token = _EVENT_SINK.set(callback)
    try:
        yield
    finally:
        _EVENT_SINK.reset(token)


def new_request_id() -> str:
    return uuid4().hex


def _safe_identifier(value: object, *, maximum: int = 160) -> str | None:
    if not isinstance(value, str) or not 1 <= len(value) <= maximum:
        return None
    if not _FIELD_RE.fullmatch(value) or _SENSITIVE_RE.search(value):
        return None
    return value


def _safe_stack(value: object) -> list[dict]:
    if not isinstance(value, list):
        return []
    frames = []
    for item in value[-15:]:
        if not isinstance(item, dict):
            continue
        filename = _safe_identifier(item.get('file'), maximum=80)
        function = _safe_identifier(item.get('function'), maximum=80)
        line = item.get('line')
        if filename and function and type(line) is int and 0 <= line < 10_000_000:
            frames.append({'file': filename, 'function': function, 'line': line})
    return frames


def _safe_fields(fields: dict, *, private: bool) -> dict:
    out = {}
    for key, value in fields.items():
        if key not in SAFE_FIELDS or key in ('request_id', 'session_id') or value is None:
            continue
        if key == 'stack_trace':
            if private:
                out[key] = _safe_stack(value)
        elif type(value) is bool:
            out[key] = value
        elif type(value) in (int, float):
            if math.isfinite(value) and 0 <= value <= 1e15:
                out[key] = value
        else:
            safe = _safe_identifier(value)
            if safe:
                out[key] = safe
    return out


def _event_payload(event: str, level: str, fields: dict) -> dict:
    name = event if isinstance(event, str) and _EVENT_RE.fullmatch(event) else 'invalid_event'
    payload = {
        'timestamp': datetime.now(timezone.utc).isoformat(timespec='milliseconds'),
        'level': level if level in ('DEBUG', 'INFO', 'WARNING', 'ERROR') else 'INFO',
        'event': name,
    }
    for key, value in (('request_id', request_id()), ('session_id', _SESSION_ID.get())):
        identifier = _safe_identifier(value, maximum=64)
        if identifier:
            payload[key] = identifier
    payload.update(_safe_fields(fields, private=True))
    return payload


def log_event(event: str, *, level: str = 'INFO', **fields) -> None:
    """Fail open on logging I/O, but expose a failure counter to diagnostics."""
    global _LOG_AVAILABLE
    payload = _event_payload(event, level, fields)
    with _LOCK:
        previous_failures = _WRITE_FAILURES
    try:
        _logger().log(getattr(logging, payload['level']), payload['event'],
                      extra={'event_payload': payload})
    except Exception as error:
        _mark_log_failure(error)
    else:
        # SafeRotatingFileHandler.handleError increments the failure counter
        # even if logging's own emit() swallowed an exception.
        with _LOCK:
            if _WRITE_FAILURES == previous_failures:
                _LOG_AVAILABLE = True
    sink = _EVENT_SINK.get()
    if sink is not None:
        safe = {key: value for key, value in payload.items()
                if key in UI_FIELDS or key in ('timestamp', 'level', 'event')}
        try:
            sink(safe)
        except Exception:
            # SSE disconnect must not alter business execution.
            pass


def log_exception(event: str, error: BaseException, **fields) -> None:
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


def _read_log_lines(path: Path):
    """Read with bounded allocations; discard malformed/overlong records."""
    with path.open('rb') as handle:
        while True:
            line = handle.readline(_MAX_LOG_LINE_BYTES + 1)
            if not line:
                break
            if len(line) > _MAX_LOG_LINE_BYTES or not line.endswith(b'\n'):
                # Consume the rest of a giant line without accumulating it.
                while line and not line.endswith(b'\n'):
                    line = handle.readline(_MAX_LOG_LINE_BYTES + 1)
                continue
            try:
                item = json.loads(line)
            except (ValueError, UnicodeError, TypeError):
                continue
            if (not isinstance(item, dict) or
                    not isinstance(item.get('event'), str) or
                    not _EVENT_RE.fullmatch(item['event']) or
                    item.get('level') not in ('DEBUG', 'INFO', 'WARNING', 'ERROR')):
                continue
            yield item


def _safe_view(item: dict) -> dict:
    out = {'event': item['event'], 'level': item['level']}
    timestamp = item.get('timestamp')
    if isinstance(timestamp, str) and _TIMESTAMP_RE.fullmatch(timestamp):
        out['timestamp'] = timestamp
    for key in ('request_id', 'session_id'):
        identifier = _safe_identifier(item.get(key), maximum=64)
        if identifier:
            out[key] = identifier
    out.update(_safe_fields(item, private=False))
    return out


def list_events(*, limit: int = 100, level: str | None = None,
                session_id: str | None = None, request_id: str | None = None) -> list[dict]:
    """Recent safe events; skipped malformed lines never crash the viewer."""
    target = _log_path()
    paths = [target.with_name(target.name + f'.{i}') for i in (3, 2, 1)] + [target]
    recent = deque(maxlen=2000)
    with _LOCK:
        for path in paths:
            try:
                if path.exists():
                    recent.extend(_read_log_lines(path))
            except OSError as error:
                _mark_log_failure(error)
    matching = []
    for item in reversed(recent):
        if level and item.get('level') != level:
            continue
        if session_id and item.get('session_id') != session_id:
            continue
        if request_id and item.get('request_id') != request_id:
            continue
        matching.append(_safe_view(item))
        if len(matching) >= min(max(limit, 1), 200):
            break
    return matching
