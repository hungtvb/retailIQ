"""Local-only chat session REST endpoints."""
from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel, Field
from retailiq.infrastructure.sessions import create_session, get_session, list_sessions, delete_session

router = APIRouter(prefix='/api/sessions', tags=['conversations'])

class NewSession(BaseModel):
    title: str = Field(default='New conversation', max_length=80)

@router.post('', status_code=201)
def new_session(body: NewSession = NewSession()):
    return create_session(body.title)

@router.get('')
def sessions():
    return {'sessions': list_sessions()}

@router.get('/{session_id}')
def session(session_id: str):
    result = get_session(session_id)
    if result is None:
        raise HTTPException(status_code=404, detail='Session not found')
    return result

@router.delete('/{session_id}', status_code=204)
def remove_session(session_id: str):
    if not delete_session(session_id):
        raise HTTPException(status_code=404, detail='Session not found')
    return Response(status_code=204)
