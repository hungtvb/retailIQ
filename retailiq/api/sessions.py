"""Local-only chat session REST endpoints."""
from fastapi import APIRouter, HTTPException, Response, Request
from retailiq.api.auth import _principal
from retailiq.infrastructure import auth
from pydantic import BaseModel, Field
from retailiq.observability import log_event, bind_context
from retailiq.infrastructure.sessions import create_session, get_session, list_sessions, delete_session, session_mutation, SessionBusyError, get_execution_trace, get_customer_memory, save_customer_memory

router = APIRouter(prefix='/api/sessions', tags=['conversations'])

class NewSession(BaseModel):
    title: str = Field(default='New conversation', max_length=80)

@router.post('', status_code=201)
def new_session(request: Request, body: NewSession = NewSession()):
    principal = _principal(request)
    auth.assert_active(principal)
    try:
        session = create_session(body.title, owner_user_id=principal.user_id,
                                 principal=principal)
    except PermissionError:
        raise HTTPException(status_code=401, detail='Authentication required') from None
    with bind_context(session=session['id']):
        log_event('chat.session_created')
    return session

@router.get('')
def sessions(request: Request):
    return {'sessions': list_sessions(owner_user_id=_principal(request).user_id)}

@router.get('/{session_id}')
def session(session_id: str, request: Request):
    result = get_session(session_id, owner_user_id=_principal(request).user_id)
    if result is None:
        raise HTTPException(status_code=404, detail='Session not found')
    return result

class CustomerMemoryBody(BaseModel):
    # Explicit opt-in: no implicit extraction from arbitrary chat messages.
    consent: bool
    preferences: dict[str, str] = Field(default_factory=dict, max_length=2)


@router.get('/{session_id}/memory')
def customer_memory(session_id: str, request: Request):
    try:
        return get_customer_memory(session_id, owner_user_id=_principal(request).user_id)
    except KeyError:
        raise HTTPException(status_code=404, detail='Session not found') from None


@router.put('/{session_id}/memory')
def update_customer_memory(session_id: str, body: CustomerMemoryBody, request: Request):
    principal = _principal(request)
    auth.assert_active(principal)
    try:
        with session_mutation(session_id):
            return save_customer_memory(session_id, consent=body.consent,
                                        preferences=body.preferences,
                                        owner_user_id=principal.user_id, principal=principal)
    except KeyError:
        raise HTTPException(status_code=404, detail='Session not found') from None
    except PermissionError:
        raise HTTPException(status_code=401, detail='Authentication required') from None
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from None
    except SessionBusyError:
        raise HTTPException(status_code=409, detail='Session is processing another request') from None


@router.delete('/{session_id}/memory', status_code=204)
def clear_customer_memory(session_id: str, request: Request):
    principal = _principal(request)
    auth.assert_active(principal)
    try:
        with session_mutation(session_id):
            save_customer_memory(session_id, consent=False, preferences={},
                                 owner_user_id=principal.user_id, principal=principal)
    except KeyError:
        raise HTTPException(status_code=404, detail='Session not found') from None
    except PermissionError:
        raise HTTPException(status_code=401, detail='Authentication required') from None
    except SessionBusyError:
        raise HTTPException(status_code=409, detail='Session is processing another request') from None
    return Response(status_code=204)


@router.get('/{session_id}/traces/{request_id}')
def execution_trace(session_id: str, request_id: str, request: Request):
    owner = _principal(request).user_id
    if get_session(session_id, owner_user_id=owner, include_messages=False) is None:
        raise HTTPException(status_code=404, detail='Session not found')
    result = get_execution_trace(session_id, request_id, owner_user_id=owner)
    if result is None:
        raise HTTPException(status_code=404, detail='Execution trace not recorded')
    return result


@router.delete('/{session_id}', status_code=204)
def remove_session(session_id: str, request: Request):
    principal = _principal(request)
    auth.assert_active(principal)
    try:
        with session_mutation(session_id):
            if get_session(session_id, owner_user_id=principal.user_id,
                           include_messages=False) is None:
                raise HTTPException(status_code=404, detail='Session not found')
            # Checkpoints live in another local SQLite store. Keep the auth
            # writer lock across their cleanup and session DELETE so logout
            # cannot commit first and still allow checkpoint mutation.
            from retailiq.orchestration.week1_graph import delete_session_checkpoints

            def cleanup_checkpoints():
                try:
                    delete_session_checkpoints(session_id)
                except Exception as error:
                    log_event('chat.checkpoint_delete_failed', level='ERROR',
                              error_type=type(error).__name__)
                    raise HTTPException(status_code=503,
                                        detail='Checkpoint cleanup failed') from None

            delete_session(session_id, owner_user_id=principal.user_id,
                           principal=principal, before_delete=cleanup_checkpoints)
    except PermissionError:
        raise HTTPException(status_code=401, detail='Authentication required') from None
    except SessionBusyError:
        raise HTTPException(status_code=409, detail='Session is processing another request') from None
    with bind_context(session=session_id):
        log_event('chat.session_deleted')
    return Response(status_code=204)
