"""Same-origin local login/logout. Credentials cannot be supplied to graph nodes."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from retailiq.infrastructure import auth
from retailiq.security import SecurityContext

router = APIRouter(prefix="/api/auth", tags=["local-auth"])


class Credentials(BaseModel):
    model_config = ConfigDict(extra="forbid")
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=256)


def _principal(request: Request) -> SecurityContext:
    principal = getattr(request.state, "principal", None)
    if not isinstance(principal, SecurityContext):
        raise HTTPException(status_code=401, detail="Authentication required")
    return principal


@router.post("/login")
def login(body: Credentials, request: Request):
    peer = request.client.host if request.client else "unknown"
    user_id = auth.authenticate_credentials(body.username, body.password, peer)
    if user_id is None:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    try:
        token, _csrf = auth.issue_auth_session(user_id)
    except ValueError:
        raise HTTPException(status_code=401, detail="Invalid credentials") from None
    user = auth.safe_user(user_id)
    if user is None:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    response = JSONResponse(user, headers={"Cache-Control": "no-store"})
    response.set_cookie(
        key=auth.COOKIE_NAME, value=token, max_age=auth.SESSION_TTL_SECONDS,
        path="/", httponly=True, samesite="strict",
        secure=request.url.scheme == "https",
    )
    return response


@router.get("/me")
def current_user(request: Request):
    principal = _principal(request)
    user = auth.safe_user(principal.user_id)
    if user is None:
        raise HTTPException(status_code=401, detail="Authentication required")
    return JSONResponse(
        {**user, "csrf_token": auth.csrf_for_principal(principal)},
        headers={"Cache-Control": "no-store"},
    )


@router.post("/logout")
def logout(request: Request):
    principal = _principal(request)
    auth.revoke_session(principal)
    response = JSONResponse({"ok": True}, headers={"Cache-Control": "no-store"})
    response.delete_cookie(key=auth.COOKIE_NAME, path="/", samesite="strict",
                           secure=request.url.scheme == "https", httponly=True)
    return response
