from fastapi import FastAPI,HTTPException
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel,Field
from retailiq.assistant import ask
from pathlib import Path
from retailiq.api.roi import router as roi_router
app=FastAPI(title='RetailIQ Copilot - Week 1')
app.include_router(roi_router)
app.mount('/assets', StaticFiles(directory=Path(__file__).resolve().parents[2]/'web'/'assets'), name='assets')
class AskBody(BaseModel): question:str=Field(min_length=3,max_length=500)
@app.get('/',response_class=HTMLResponse)
def home():return (Path(__file__).resolve().parents[2]/'web'/'index.html').read_text(encoding='utf8')
@app.post('/ask')
def answer(data:AskBody):
 try:return ask(data.question)
 except Exception as e:
  # Never echo raw provider error (which can include endpoint or request data) to browser.
  raise HTTPException(status_code=503,detail=f"Request failed ({type(e).__name__}); check OpenAI-compatible API configuration") from None
@app.get('/health')
def health():return {'status':'ok'}
