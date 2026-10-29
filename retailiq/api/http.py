"""FastAPI Web UI and local demo chat API."""
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, StreamingResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from retailiq.assistant import ask
from retailiq.rag.indexing import IndexNotReadyError
from retailiq.infrastructure.sessions import history, add_turn, get_session, session_mutation, SessionBusyError, save_execution_trace
from pathlib import Path
from contextlib import nullcontext
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
from retailiq.api.workflows import router as workflows_router
from fastapi import Request

# Bound streaming capacity: prevent slow providers or disconnected clients
# from spawning an unlimited number of background execution threads.
_STREAM_WORKER_SLOTS = threading.BoundedSemaphore(value=8)
_STREAM_QUEUE_LIMIT = 128

app = FastAPI(title='RetailIQ Copilot - Four-Week Local Demo')
app.include_router(roi_router)
app.include_router(sessions_router)
app.include_router(logs_router)
app.include_router(workflows_router)
app.mount('/assets', StaticFiles(directory=Path(__file__).resolve().parents[2] / 'web' / 'assets'), name='assets')

# New product UI is independently built and served alongside the existing
# entrypoint until full browser/business acceptance is complete.
_WORKSPACE_DIST = Path(__file__).resolve().parents[2] / 'frontend' / 'dist'
app.mount('/workspace/assets',
          StaticFiles(directory=_WORKSPACE_DIST / 'assets', check_dir=False),
          name='product-workspace-assets')


def _safe_http_path(path: str) -> str:
    """Canonicalize route labels so customer values embedded in URLs are not logged."""
    if path.startswith('/api/workflows/'):
        return '/api/workflows/{operation}'
    if path in ('/ask', '/ask/stream', '/api/sessions', '/api/roi/defaults', '/api/roi/estimate'):
        return path
    if re.fullmatch(r'/api/sessions/[0-9a-fA-F-]{36}', path):
        return '/api/sessions/{session_id}'
    if path.startswith('/api/logs'):
        return '/api/logs'
    return '/api/other' if path.startswith('/api/') else '/other'


def _local_demo_request(request: Request) -> bool:
    """Defense in depth for the unauthenticated Week 1 single-host demo.

    Both peer IP and Host must be local. Not a replacement for user auth or
    trustworthy proxy configuration; do not deploy this app publicly.
    """
    client_host = request.client.host if request.client else ''
    host = request.headers.get('host', '').lower().strip()
    permitted_peer = client_host in {'127.0.0.1', '::1', 'testclient'}
    permitted_host = host in {'localhost', '127.0.0.1', 'testserver', '[::1]'} or (
        any(host.startswith(h + ':') and host[len(h) + 1:].isdigit()
            for h in ('localhost', '127.0.0.1', 'testserver', '[::1]')))
    return permitted_peer and permitted_host


@app.middleware('http')
async def record_http(request: Request, call_next):
    if not _local_demo_request(request):
        return JSONResponse(status_code=403, content={
            'detail': 'Remote access is unavailable. Connect through the configured trusted host.'
        })
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


def _missing_module_message(error: ModuleNotFoundError) -> str:
    """Expose actionable package guidance without revealing arbitrary import paths."""
    name = error.name or ''
    if name.startswith('retailiq'):
        return ('RetailIQ source modules are out of sync. Update the project files '
                'and restart the server with the project root as the working directory.')
    supported = {
        'langgraph', 'langgraph.checkpoint', 'langgraph.checkpoint.sqlite',
        'langchain', 'langchain_core', 'langchain_openai', 'langchain_chroma',
        'chromadb', 'langchain_community', 'openai', 'pydantic', 'dotenv',
    }
    label = f"Python module '{name}' is missing. " if name in supported else 'A required Python module is missing. '
    return (label + 'Run python -m pip install -r requirements-full.txt '
            'in the same Python environment used to start RetailIQ, then restart the server.')


class AskBody(BaseModel):
    question: str = Field(min_length=3, max_length=500)
    session_id: str | None = Field(default=None, min_length=36, max_length=36)


@app.get('/workspace', response_class=HTMLResponse)
@app.get('/workspace/', response_class=HTMLResponse)
def product_workspace():
    index = _WORKSPACE_DIST / 'index.html'
    if not index.is_file():
        raise HTTPException(status_code=503,
                            detail='Workspace has not been built. Run npm install && npm run build in frontend/.')
    return index.read_text(encoding='utf8')


@app.get('/', response_class=HTMLResponse)
def home():
    return (Path(__file__).resolve().parents[2] / 'web' / 'index.html').read_text(encoding='utf8')


def _perform_turn(data: AskBody) -> dict:
    """One shared execution path for ordinary POST and live streamed POST."""
    guard = session_mutation(data.session_id) if data.session_id else nullcontext()
    with guard:
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
                add_turn(data.session_id, data.question, {**result, 'request_id': request_id()})
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
        except SessionBusyError:
            raise HTTPException(status_code=409, detail='Session is processing another request') from None
        except IndexNotReadyError as error:
            log_exception('chat.knowledge_index_unavailable', error)
            raise HTTPException(status_code=503,
                                detail='Product knowledge index unavailable; run scripts/index_products.py') from None
        except ModuleNotFoundError as error:
            log_exception('chat.dependency_missing', error)
            raise HTTPException(status_code=503, detail=_missing_module_message(error)) from None
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
    if not _STREAM_WORKER_SLOTS.acquire(blocking=False):
        raise HTTPException(status_code=503, detail='Chat streaming capacity reached; retry later',
                            headers={'Retry-After': '1'})
    rid = getattr(request.state, 'request_id', None) or new_request_id()
    events: queue.Queue = queue.Queue(maxsize=_STREAM_QUEUE_LIMIT)
    disconnected = threading.Event()

    def enqueue_final(kind, payload):
        # Model/tool may finish after the client disconnected.
        if disconnected.is_set():
            return
        # No blocked worker when a browser stops draining its event queue.
        while True:
            try:
                events.put_nowait((kind, payload))
                return
            except queue.Full:
                try:
                    events.get_nowait()
                except queue.Empty:
                    continue

    def run_agent():
        trace_events: list[dict] = []

        def push_log(payload: dict):
            # Recording is independent from the browser connection and the
            # bounded transport queue. Traces remain available after disconnect.
            if len(trace_events) < 161:
                trace_events.append(payload)
            if disconnected.is_set():
                return
            try:
                events.put_nowait(('log', payload))
            except queue.Full:
                # The durable trace still records the event if transport drops it.
                pass

        try:
            with bind_context(request=rid, session=data.session_id), bind_event_sink(push_log):
                try:
                    result = _perform_turn(data)
                    if data.session_id:
                        try:
                            save_execution_trace(data.session_id, rid, trace_events)
                        except Exception as error:
                            # Telemetry persistence cannot invalidate a saved
                            # business answer; history will truthfully say no trace.
                            log_exception('chat.trace_persist_failed', error)
                    enqueue_final('result', result)
                except SessionBusyError:
                    enqueue_final('error', {'code': 'session_busy',
                                           'message': 'This chat is already processing another request.',
                                           'request_id': rid})
                except IndexNotReadyError as error:
                    log_exception('chat.knowledge_index_unavailable', error)
                    enqueue_final('error', {'code': 'index_not_ready',
                                           'message': 'Product knowledge index unavailable; run scripts/index_products.py',
                                           'request_id': rid})
                except ModuleNotFoundError as error:
                    log_exception('chat.dependency_missing', error)
                    enqueue_final('error', {'code': 'dependency_missing',
                                           'message': _missing_module_message(error),
                                           'request_id': rid})
                except Exception as error:
                    log_exception('chat.execution_failed', error)
                    enqueue_final('error', {'code': 'execution_failed',
                                           'message': 'Agent execution failed; check execution logs.',
                                           'request_id': rid})
                finally:
                    enqueue_final('done', {'request_id': rid})
        finally:
            # A completed worker frees capacity, regardless of browser state.
            _STREAM_WORKER_SLOTS.release()

    # Own the resource slot from worker start until completion even if
    # StreamingResponse is never consumed by the caller.
    worker = threading.Thread(target=run_agent, name='retailiq-chat-stream', daemon=True)
    try:
        worker.start()
    except BaseException:
        _STREAM_WORKER_SLOTS.release()
        raise

    def live_events():
        try:
            yield _sse('started', {'request_id': rid, 'session_id': data.session_id,
                                   'transport': 'sse', 'stream_kind': 'execution_events'})
            while True:
                try:
                    kind, payload = events.get(timeout=10)
                except queue.Empty:
                    if not worker.is_alive() and events.empty():
                        yield _sse('error', {'code': 'worker_exited', 'request_id': rid,
                                            'message': 'Stream worker stopped unexpectedly'})
                        yield _sse('done', {'request_id': rid})
                        break
                    yield ': heartbeat\n\n'
                    continue
                if kind == 'done':
                    yield _sse('done', payload)
                    break
                yield _sse(kind, payload)
        finally:
            # Stops queueing events, not an already-running synchronous LLM.
            disconnected.set()

    return StreamingResponse(live_events(), media_type='text/event-stream', headers={
        'Cache-Control': 'no-cache, no-store',
        'X-Accel-Buffering': 'no',
        'X-Content-Type-Options': 'nosniff',
    })

@app.get('/health')
def health():
    return {'status': 'ok'}
