"""FastAPI Web UI and local demo chat API."""
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from retailiq.assistant import ask
from retailiq.infrastructure.sessions import history, add_turn, get_session
from pathlib import Path
import time
import re
import json
import queue
import threading
import os
from retailiq.observability import bind_context, new_request_id, log_event, log_exception, observed, request_id, bind_event_sink
from retailiq.api.roi import router as roi_router
from retailiq.api.sessions import router as sessions_router
from retailiq.api.logs import router as logs_router
from fastapi import Request

app = FastAPI(title='RetailIQ Copilot - Week 1 Multi-Agent')
app.include_router(roi_router)
app.include_router(sessions_router)
app.include_router(logs_router)
app.mount('/assets', StaticFiles(directory=Path(__file__).resolve().parents[2] / 'web' / 'assets'), name='assets')


def _safe_http_path(path: str) -> str:
    """Canonicalize route labels so customer values embedded in URLs are not logged."""
    if path in ('/ask', '/ask/stream', '/api/sessions', '/api/roi/defaults', '/api/roi/estimate'):
        return path
    if re.fullmatch(r'/api/sessions/[0-9a-fA-F-]{36}', path):
        return '/api/sessions/{session_id}'
    if path.startswith('/api/logs'):
        return '/api/logs'
    return '/api/other' if path.startswith('/api/') else '/other'


@app.middleware('http')
async def record_http(request: Request, call_next):
    rid = new_request_id()
    path = request.url.path
    safe_path = _safe_http_path(path)
    is_api = path.startswith('/api/') or path in ('/ask', '/ask/stream')
    # Avoid emitting a new log event for every read of the log viewer itself.
    is_api = is_api and safe_path != '/api/logs'
    started = time.perf_counter()
    request.state.request_id = rid
    with bind_context(request=rid):
        if is_api:
            log_event('http.request_started', method=request.method, path=safe_path)
        try:
            response = await call_next(request)
        except Exception as error:
            if is_api:
                log_exception('http.request_failed', error, method=request.method, path=safe_path,
                              duration_ms=round((time.perf_counter()-started)*1000, 2))
            raise
        response.headers['X-Request-ID'] = rid
        if is_api:
            log_event('http.response_started' if safe_path == '/ask/stream' else 'http.request_completed',
                      method=request.method, path=safe_path,
                      status_code=response.status_code,
                      duration_ms=round((time.perf_counter()-started)*1000, 2))
        return response


class AskBody(BaseModel):
    question: str = Field(min_length=3, max_length=500)
    session_id: str | None = Field(default=None, min_length=36, max_length=36)


@app.get('/', response_class=HTMLResponse)
def home():
    return (Path(__file__).resolve().parents[2] / 'web' / 'index.html').read_text(encoding='utf8')


def _perform_turn(data: AskBody) -> dict:
    """One shared execution path for ordinary POST and live streamed POST."""
    current = None
    if data.session_id is not None:
        current = get_session(data.session_id, include_messages=False)
        if current is None:
            raise KeyError('Session not found')
    with observed('chat.turn', execution_mode='full' if os.getenv('RETAILIQ_MODE') == 'full' else 'offline'):
        if data.session_id is None:
            result = ask(data.question)
        else:
            prior = history(data.session_id, limit=12)
            result = ask(data.question, history=prior, active_agent=current['active_agent'])
            add_turn(data.session_id, data.question, result)
    log_event('chat.turn_result', agent=result.get('active_agent'),
              intent=result.get('intent'), skill=result.get('skill'),
              route_fallback=result.get('route_fallback'),
              record_count=len(result.get('records') or []),
              context_count=len(result.get('contexts') or []))
    return {**result, 'session_id': data.session_id, 'request_id': request_id()}


@app.post('/ask')
def answer(data: AskBody):
    with bind_context(session=data.session_id):
        try:
            return _perform_turn(data)
        except KeyError:
            raise HTTPException(status_code=404, detail='Session not found') from None
        except Exception as error:
            # Stack frame locations (not prompt content) are available in local JSONL.
            log_exception('chat.execution_failed', error)
            raise HTTPException(status_code=503,
                                detail=f'Request failed ({type(error).__name__}); check model configuration') from None


def _sse(kind: str, data: dict) -> str:
    return f'event: {kind}\ndata: {json.dumps(data, ensure_ascii=False, separators=(",", ":"))}\n\n'


@app.post('/ask/stream')
def stream_answer(data: AskBody, request: Request):
    """Live SSE progress over fetch(POST); final result is persisted exactly once.

    Each stream owns its queue and its log callback. Logs are actual execution
    events emitted by the same backend functions that write rotating JSONL.
    This is event streaming, not token-by-token LLM generation.
    """
    if data.session_id and get_session(data.session_id, include_messages=False) is None:
        raise HTTPException(status_code=404, detail='Session not found')
    rid = getattr(request.state, 'request_id', None) or new_request_id()
    events: queue.Queue = queue.Queue(maxsize=512)

    def run_agent():
        def push_log(payload: dict):
            try:
                events.put_nowait(('log', payload))
            except queue.Full:
                # Agent execution continues even when the UI cannot keep up.
                pass

        with bind_context(request=rid, session=data.session_id), bind_event_sink(push_log):
            try:
                result = _perform_turn(data)
                events.put(('result', result))
            except Exception as error:
                log_exception('chat.execution_failed', error)
                events.put(('error', {'code': 'execution_failed',
                                      'message': 'Agent execution failed; check local diagnostics.',
                                      'request_id': rid}))
            finally:
                events.put(('done', {'request_id': rid}))

    def live_events():
        # Worker begins as soon as the response body is consumed; no precomputed logs.
        thread = threading.Thread(target=run_agent, name='retailiq-chat-stream', daemon=True)
        thread.start()
        yield _sse('started', {'request_id': rid, 'session_id': data.session_id,
                               'transport': 'sse', 'stream_kind': 'execution_events'})
        while True:
            try:
                kind, payload = events.get(timeout=10)
            except queue.Empty:
                yield ': heartbeat\n\n'
                continue
            if kind == 'done':
                yield _sse('done', payload)
                break
            yield _sse(kind, payload)

    return StreamingResponse(live_events(), media_type='text/event-stream', headers={
        'Cache-Control': 'no-cache, no-store',
        'X-Accel-Buffering': 'no',
        'X-Content-Type-Options': 'nosniff',
    })

@app.get('/health')
def health():
    return {'status': 'ok'}
