"""Local-only chat session REST endpoints."""
from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel, Field
from retailiq.observability import log_event, bind_context
from retailiq.infrastructure.sessions import create_session, get_session, list_sessions, delete_session, session_mutation, SessionBusyError, get_execution_trace

router = APIRouter(prefix='/api/sessions', tags=['conversations'])

class NewSession(BaseModel):
    title: str = Field(default='New conversation', max_length=80)

@router.post('', status_code=201)
def new_session(body: NewSession = NewSession()):
    session = create_session(body.title)
    with bind_context(session=session['id']):
        log_event('chat.session_created')
    return session

@router.get('')
def sessions():
    return {'sessions': list_sessions()}

@router.get('/{session_id}')
def session(session_id: str):
    result = get_session(session_id)
    if result is None:
        raise HTTPException(status_code=404, detail='Session not found')
    return result

@router.get('/{session_id}/traces/{request_id}')
def execution_trace(session_id: str, request_id: str):
    if get_session(session_id, include_messages=False) is None:
        raise HTTPException(status_code=404, detail='Session not found')
    result = get_execution_trace(session_id, request_id)
    if result is None:
        raise HTTPException(status_code=404, detail='Execution trace not recorded')
    return result


@router.delete('/{session_id}', status_code=204)
def remove_session(session_id: str):
    try:
        with session_mutation(session_id):
            if get_session(session_id, include_messages=False) is None:
                raise HTTPException(status_code=404, detail='Session not found')
            # Remove graph state first; if it fails, retain the session for retry.
            from retailiq.orchestration.week1_graph import delete_session_checkpoints
            try:
                delete_session_checkpoints(session_id)
            except Exception as error:
                log_event('chat.checkpoint_delete_failed', level='ERROR',
                          error_type=type(error).__name__)
                raise HTTPException(status_code=503, detail='Checkpoint cleanup failed') from None
            delete_session(session_id)
    except SessionBusyError:
        raise HTTPException(status_code=409, detail='Session is processing another request') from None
    with bind_context(session=session_id):
        log_event('chat.session_deleted')
    return Response(status_code=204)
