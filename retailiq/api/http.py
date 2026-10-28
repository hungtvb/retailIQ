"""FastAPI Web UI and local demo chat API."""
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from retailiq.assistant import ask
from retailiq.infrastructure.sessions import history, add_turn, get_session
from pathlib import Path
from retailiq.api.roi import router as roi_router
from retailiq.api.sessions import router as sessions_router

app = FastAPI(title='RetailIQ Copilot - Week 1 Multi-Agent')
app.include_router(roi_router)
app.include_router(sessions_router)
app.mount('/assets', StaticFiles(directory=Path(__file__).resolve().parents[2] / 'web' / 'assets'), name='assets')


class AskBody(BaseModel):
    question: str = Field(min_length=3, max_length=500)
    session_id: str | None = Field(default=None, min_length=36, max_length=36)


@app.get('/', response_class=HTMLResponse)
def home():
    return (Path(__file__).resolve().parents[2] / 'web' / 'index.html').read_text(encoding='utf8')


@app.post('/ask')
def answer(data: AskBody):
    if data.session_id is not None:
        current = get_session(data.session_id, include_messages=False)
        if current is None:
            raise HTTPException(status_code=404, detail='Session not found')
    try:
        if data.session_id is None:
            # Preserve old one-off API contract; no accidental implicit session.
            return ask(data.question)
        prior = history(data.session_id, limit=12)
        result = ask(data.question, history=prior, active_agent=current['active_agent'])
        add_turn(data.session_id, data.question, result)
        return {**result, 'session_id': data.session_id}
    except KeyError:
        raise HTTPException(status_code=404, detail='Session not found') from None
    except Exception as e:
        # Do not expose secrets, endpoints, or raw prompt text in the response.
        raise HTTPException(status_code=503,
                            detail=f'Request failed ({type(e).__name__}); check model configuration') from None


@app.get('/health')
def health():
    return {'status': 'ok'}
