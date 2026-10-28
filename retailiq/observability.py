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
import math
import re
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
# A per-request live subscriber, scoped with contextvars; never broadcast to other sessions.
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
_EVENT_RE = re.compile(r'^[a-z][a-z0-9_.-]{0,79}
# Strict allowlist prevents accidental prompt, credentials, URL, or response logging.
SAFE_FIELDS = frozenset({
    'agent', 'previous_agent', 'target_agent', 'intent', 'skill', 'tool',
    'status', 'status_code', 'method', 'path', 'duration_ms', 'route_fallback',
    'execution_mode', 'error_type', 'record_count', 'context_count',
    'subagent', 'input_tokens', 'output_tokens', 'session_id',
    'request_id', 'stack_trace',
})
UI_FIELDS = SAFE_FIELDS - {'stack_trace'}


def _log_path() -> Path:
    return Path(os.environ.get('RETAILIQ_LOG_FILE') or DEFAULT_LOG).expanduser().resolve()


def _mark_log_failure(error: BaseException) -> None:
    """Track only exception class; never print paths, payloads or credentials."""
    global _WRITE_FAILURES, _LAST_ERROR_TYPE, _LOG_AVAILABLE
    with _LOCK:
        _WRITE_FAILURES += 1
        _LAST_ERROR_TYPE = type(error).__name__
        _LOG_AVAILABLE = False


def log_health() -> dict:
    """In-process diagnostics; not a guarantee of durable delivery."""
    with _LOCK:
        return {'available': _LOG_AVAILABLE, 'write_failures': _WRITE_FAILURES,
                'last_error_type': _LAST_ERROR_TYPE}


class SafeRotatingFileHandler(RotatingFileHandler):
    def handleError(self, record: logging.LogRecord) -> None:
        # Standard logging.handleError prints traceback/messages to stderr in
        # debug builds, potentially exposing private paths or event payloads.
        import sys
        error = sys.exc_info()[1]
        _mark_log_failure(error if error is not None else OSError())


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
            handler = SafeRotatingFileHandler(target, maxBytes=2_000_000,
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
    """Emit the same redacted events to a single in-flight SSE request.

    This is synchronous and scoped to the worker context. Stored logs and the
    UI always share the same allowlist; no raw prompts or stack frames escape.
    """
    token = _EVENT_SINK.set(callback)
    try:
        yield
    finally:
        _EVENT_SINK.reset(token)


def new_request_id() -> str:
    return uuid4().hex


def _safe_identifier(value: object, *, maximum: int = 160) -> str | None:
    if not isinstance(value, str) or not value or len(value) > maximum:
        return None
    if not _FIELD_RE.fullmatch(value) or _SENSITIVE_RE.search(value):
        return None
    return value


def _safe_stack(value: object) -> list[dict]:
    if not isinstance(value, list):
        return []
    result = []
    for frame in value[-15:]:
        if not isinstance(frame, dict):
            continue
        filename = _safe_identifier(frame.get('file'), maximum=80)
        function = _safe_identifier(frame.get('function'), maximum=80)
        line = frame.get('line')
        if filename and function and type(line) is int and 0 <= line <= 10_000_000:
            result.append({'file': filename, 'function': function, 'line': line})
    return result


def _event_payload(event: str, level: str, fields: dict) -> dict:
    event_name = event if isinstance(event, str) and _EVENT_RE.fullmatch(event) else 'invalid_event'
    payload = {
        'timestamp': datetime.now(timezone.utc).isoformat(timespec='milliseconds'),
        'level': level if level in ('DEBUG', 'INFO', 'WARNING', 'ERROR') else 'INFO',
        'event': event_name,
    }
    for context_key, value in (('request_id', request_id()), ('session_id', _SESSION_ID.get())):
        safe = _safe_identifier(value, maximum=64)
        if safe:
            payload[context_key] = safe
    for key, value in fields.items():
        if key not in SAFE_FIELDS or value is None or key in ('request_id', 'session_id'):
            continue
        if key == 'stack_trace':
            payload[key] = _safe_stack(value)
        elif type(value) is bool:
            payload[key] = value
        elif type(value) in (int, float) and math.isfinite(value):
            if 0 <= value <= 1e15:
                payload[key] = value
        elif isinstance(value, str):
            safe = _safe_identifier(value)
            if safe:
                payload[key] = safe
    return payload


def log_event(event: str, *, level: str = 'INFO', **fields) -> None:
    """Best-effort safe logging; business execution never depends on log I/O."""
    payload = _event_payload(event, level, fields)
    try:
        logger = _logger()
        logger.log(getattr(logging, payload['level']), payload['event'],
                   extra={'event_payload': payload})
        # Handler output may have failed internally; handleError records that
        # without raising or writing sensitive data to stderr.
    except Exception as error:
        _mark_log_failure(error)
    else:
        # Successful logger setup does not prove emit succeeded; a handler
        # reporting an error explicitly sets _LOG_AVAILABLE=False.
        pass
    sink = _EVENT_SINK.get()
    if sink is not None:
        sanitized = {k: v for k, v in payload.items()
                     if k in UI_FIELDS or k in ('timestamp', 'level', 'event')}
        try:
            sink(sanitized)
        except Exception:
            pass


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


def _read_log_lines(path: Path):
    """Skip corrupt or oversized records with bounded per-line allocations."""
    with path.open('rb') as handle:
        while True:
            line = handle.readline(_MAX_LOG_LINE_BYTES + 1)
            if not line:
                break
            if len(line) > _MAX_LOG_LINE_BYTES or not line.endswith(b'\\n'):
                # A large/malformed record may span multiple bounded reads.
                while line and not line.endswith(b'\\n'):
                    line = handle.readline(_MAX_LOG_LINE_BYTES + 1)
                continue
            try:
                item = json.loads(line)
            except (ValueError, UnicodeError, TypeError):
                continue
            if not isinstance(item, dict):
                continue
            event = item.get('event')
            level = item.get('level')
            if not isinstance(event, str) or not _EVENT_RE.fullmatch(event):
                continue
            if level not in ('DEBUG', 'INFO', 'WARNING', 'ERROR'):
                continue
            yield item


def list_events(*, limit: int = 100, level: str | None = None,
                session_id: str | None = None, request_id: str | None = None) -> list[dict]:
    """Return bounded, validated, newest-first events from local rotating logs."""
    target = _log_path()
    paths = [target.with_name(target.name + f'.{i}') for i in (3, 2, 1)] + [target]
    recent = deque(maxlen=2000)
    with _LOCK:
        for path in paths:
            try:
                if path.exists():
                    for item in _read_log_lines(path):
                        recent.append(item)
            except OSError as error:
                _mark_log_failure(error)
                continue
    matching = []
    for item in reversed(recent):
        if level and item.get('level') != level:
            continue
        if session_id and item.get('session_id') != session_id:
            continue
        if request_id and item.get('request_id') != request_id:
            continue
        # Revalidate even manually modified historical JSONL: no raw arbitrary
        # strings from files escape through the diagnostic API.
        safe = _event_payload(item['event'], item['level'],
                              {key: value for key, value in item.items() if key in UI_FIELDS})
        for key in ('request_id', 'session_id', 'timestamp'):
            val = item.get(key)
            if key == 'timestamp':
                if isinstance(val, str) and len(val) <= 40:
                    safe[key] = val
            else:
                identifier = _safe_identifier(val, maximum=64)
                if identifier:
                    safe[key] = identifier
        safe.pop('stack_trace', None)
        matching.append(safe)
        if len(matching) >= min(max(limit, 1), 200):
            break
    return matching
)
_FIELD_RE = re.compile(r'^[A-Za-z0-9_./:{}-]{1,160}
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
    """Emit the same redacted events to a single in-flight SSE request.

    This is synchronous and scoped to the worker context. Stored logs and the
    UI always share the same allowlist; no raw prompts or stack frames escape.
    """
    token = _EVENT_SINK.set(callback)
    try:
        yield
    finally:
        _EVENT_SINK.reset(token)


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
    sink = _EVENT_SINK.get()
    if sink is not None:
        sanitized = {k: v for k, v in payload.items()
                     if k in UI_FIELDS or k in ('timestamp', 'level', 'event')}
        try:
            sink(sanitized)
        except Exception:
            # An interrupted viewer must not crash the agent or its durable log.
            pass


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
)
_SENSITIVE_RE = re.compile(r'(?:sk-[A-Za-z0-9]|bearer|api[_-]?key|secret|password|token)', re.I)

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
    """Emit the same redacted events to a single in-flight SSE request.

    This is synchronous and scoped to the worker context. Stored logs and the
    UI always share the same allowlist; no raw prompts or stack frames escape.
    """
    token = _EVENT_SINK.set(callback)
    try:
        yield
    finally:
        _EVENT_SINK.reset(token)


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
    sink = _EVENT_SINK.get()
    if sink is not None:
        sanitized = {k: v for k, v in payload.items()
                     if k in UI_FIELDS or k in ('timestamp', 'level', 'event')}
        try:
            sink(sanitized)
        except Exception:
            # An interrupted viewer must not crash the agent or its durable log.
            pass


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
