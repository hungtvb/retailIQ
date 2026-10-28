"""FastAPI Web UI and local demo chat API."""
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from retailiq.assistant import ask
from retailiq.infrastructure.sessions import history, add_turn, get_session
from pathlib import Path
import time
from retailiq.observability import bind_context, new_request_id, log_event, log_exception, observed, request_id
from retailiq.api.roi import router as roi_router
from retailiq.api.sessions import router as sessions_router
from retailiq.api.logs import router as logs_router
from fastapi import Request

app = FastAPI(title='RetailIQ Copilot - Week 1 Multi-Agent')
app.include_router(roi_router)
app.include_router(sessions_router)
app.include_router(logs_router)
app.mount('/assets', StaticFiles(directory=Path(__file__).resolve().parents[2] / 'web' / 'assets'), name='assets')


@app.middleware('http')
async def record_http(request: Request, call_next):
    rid = new_request_id()
    path = request.url.path
    is_api = path.startswith('/api/') or path == '/ask'
    # Avoid emitting a new log event for every read of the log viewer itself.
    is_api = is_api and not path.startswith('/api/logs')
    started = time.perf_counter()
    with bind_context(request=rid):
        if is_api:
            log_event('http.request_started', method=request.method, path=path)
        try:
            response = await call_next(request)
        except Exception as error:
            if is_api:
                log_exception('http.request_failed', error, method=request.method, path=path,
                              duration_ms=round((time.perf_counter()-started)*1000, 2))
            raise
        response.headers['X-Request-ID'] = rid
        if is_api:
            log_event('http.request_completed', method=request.method, path=path,
                      status_code=response.status_code,
                      duration_ms=round((time.perf_counter()-started)*1000, 2))
        return response


class AskBody(BaseModel):
    question: str = Field(min_length=3, max_length=500)
    session_id: str | None = Field(default=None, min_length=36, max_length=36)


@app.get('/', response_class=HTMLResponse)
def home():
    return (Path(__file__).resolve().parents[2] / 'web' / 'index.html').read_text(encoding='utf8')


@app.post('/ask')
def answer(data: AskBody):
    with bind_context(session=data.session_id):
        if data.session_id is not None:
            current = get_session(data.session_id, include_messages=False)
            if current is None:
                raise HTTPException(status_code=404, detail='Session not found')
        try:
            with observed('chat.turn', execution_mode='full' if __import__('os').environ.get('RETAILIQ_MODE')=='full' else 'offline'):
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
            return {**result, 'session_id': data.session_id,
                    'request_id': request_id()}
        except KeyError:
            raise HTTPException(status_code=404, detail='Session not found') from None
        except Exception as error:
            # Error detail excludes exception message, prompt, provider URL and secrets.
            raise HTTPException(status_code=503,
                                detail=f'Request failed ({type(error).__name__}); check model configuration') from None


@app.get('/health')
def health():
    return {'status': 'ok'}
