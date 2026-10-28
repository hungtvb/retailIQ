"""Local-only, read-only event viewer; never returns prompts or exception stacks."""
from ipaddress import ip_address
from fastapi import APIRouter, HTTPException, Query, Request, Response
from retailiq.observability import list_events

router = APIRouter(prefix='/api/logs', tags=['observability'])


def _local_host(host: str | None) -> bool:
    if host in ('testclient', 'localhost'):
        return True
    try:
        return bool(host and ip_address(host).is_loopback)
    except ValueError:
        return False


@router.get('')
def events(request: Request, response: Response,
           limit: int = Query(80, ge=1, le=200),
           level: str | None = Query(default=None, pattern='^(INFO|WARNING|ERROR|DEBUG)$'),
           session_id: str | None = Query(default=None, min_length=36, max_length=36),
           request_id: str | None = Query(default=None, min_length=32, max_length=36)):
    if not _local_host(request.client.host if request.client else None):
        raise HTTPException(status_code=403, detail='Local-only diagnostics')
    response.headers['Cache-Control'] = 'no-store'
    response.headers['X-Content-Type-Options'] = 'nosniff'
    return {'events': list_events(limit=limit, level=level,
                                  session_id=session_id, request_id=request_id),
            'source': 'local_rotating_jsonl', 'note': 'No prompts, keys, or stack traces in UI'}
