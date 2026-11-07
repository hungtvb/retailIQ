"""Local two-role identity/session store (application SQLite, never Fiction)."""
from __future__ import annotations

from hashlib import sha256
import re
import secrets
from sqlite3 import IntegrityError
import time
from uuid import uuid4

from pwdlib import PasswordHash

from retailiq.infrastructure.sessions import _connect, _path
from retailiq.security import SecurityContext


COOKIE_NAME = "retailiq_sid"
SESSION_TTL_SECONDS = 8 * 60 * 60
ATTEMPT_WINDOW_SECONDS = 15 * 60
LOCK_SECONDS = 15 * 60
MAX_FAILED_ATTEMPTS = 5
_PASSWORD_HASH = PasswordHash.recommended()
# Public, non-secret Argon2id dummy hash from FastAPI's password tutorial.
_DUMMY_HASH = "$argon2id$v=19$m=65536,t=3,p=4$wagCPXjifgvUFBzq4hqe3w$CYaIb8sB+wtD+Vu/P4uod1+Qof8h+1g7bbDlBID48Rc"
_USERNAME = re.compile(r"[a-zA-Z0-9._-]{3,64}\Z")


def _digest(value: str) -> str:
    return sha256(value.encode("utf-8")).hexdigest()


def _schema() -> None:
    """Idempotent schema on the same SQLite file as existing conversations."""
    with _connect() as db:
        db.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id TEXT PRIMARY KEY,
            username TEXT NOT NULL UNIQUE COLLATE NOCASE,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL CHECK(role IN ('analyst','manager')),
            disabled INTEGER NOT NULL DEFAULT 0 CHECK(disabled IN (0,1)),
            created_at INTEGER NOT NULL
        );
        CREATE TABLE IF NOT EXISTS auth_sessions (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL REFERENCES users(id),
            token_hash TEXT NOT NULL UNIQUE,
            csrf_secret TEXT NOT NULL,
            created_at INTEGER NOT NULL,
            expires_at INTEGER NOT NULL,
            revoked_at INTEGER
        );
        CREATE INDEX IF NOT EXISTS ix_auth_sessions_user ON auth_sessions(user_id);
        CREATE TABLE IF NOT EXISTS auth_login_failures (
            username TEXT NOT NULL,
            peer_ip TEXT NOT NULL,
            failures INTEGER NOT NULL,
            window_start INTEGER NOT NULL,
            locked_until INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY(username,peer_ip)
        );
        """)


def create_local_user(username: str, role: str, password: str) -> str:
    """CLI-only provisioning; password hash never echoed or logged."""
    if not isinstance(username, str) or not _USERNAME.fullmatch(username):
        raise ValueError("Invalid username")
    if role not in ("analyst", "manager"):
        raise ValueError("Invalid role")
    if not isinstance(password, str) or not 12 <= len(password) <= 128:
        raise ValueError("Password must have 12 to 128 characters")
    password_hash = _PASSWORD_HASH.hash(password)
    uid = str(uuid4())
    _schema()
    try:
        with _connect() as db:
            db.execute("INSERT INTO users(id,username,password_hash,role,created_at) "
                       "VALUES(?,?,?,?,?)",
                       (uid, username, password_hash, role, int(time.time())))
    except IntegrityError as exc:
        raise ValueError("Username is unavailable") from exc
    return uid


def authenticate_credentials(username: str, password: str, peer_ip: str = "local") -> str | None:
    """Fail closed after 5 bad attempts / 15 minutes per username + local peer."""
    if not isinstance(username, str) or not isinstance(password, str):
        return None
    if len(username) > 64 or len(peer_ip) > 80 or len(password) > 256:
        return None
    name = username.casefold()
    now = int(time.time())
    _schema()
    with _connect() as db:
        previous = db.execute("SELECT failures,window_start,locked_until "
                              "FROM auth_login_failures WHERE username=? AND peer_ip=?",
                              (name, peer_ip)).fetchone()
        if previous and previous["locked_until"] > now:
            return None
        user = db.execute(
            "SELECT id,password_hash,disabled FROM users WHERE username=? COLLATE NOCASE",
            (username,)).fetchone()
    try:
        password_ok = _PASSWORD_HASH.verify(password, user["password_hash"] if user else _DUMMY_HASH)
    except (ValueError, TypeError):
        password_ok = False
    valid = bool(user and not user["disabled"] and password_ok)
    with _connect() as db:
        db.execute("BEGIN IMMEDIATE")
        previous = db.execute("SELECT failures,window_start,locked_until "
                              "FROM auth_login_failures WHERE username=? AND peer_ip=?",
                              (name, peer_ip)).fetchone()
        if previous and previous["locked_until"] > now:
            return None
        if valid:
            # A concurrent account disable must also fail closed.
            active = db.execute("SELECT disabled FROM users WHERE id=?", (user["id"],)).fetchone()
            if active and not active["disabled"]:
                db.execute("DELETE FROM auth_login_failures WHERE username=? AND peer_ip=?",
                           (name, peer_ip))
                return str(user["id"])
            valid = False
        if not previous or now - previous["window_start"] >= ATTEMPT_WINDOW_SECONDS:
            count, start = 1, now
        else:
            count, start = previous["failures"] + 1, previous["window_start"]
        db.execute(
            "INSERT INTO auth_login_failures(username,peer_ip,failures,window_start,locked_until) "
            "VALUES(?,?,?,?,?) ON CONFLICT(username,peer_ip) DO UPDATE SET "
            "failures=excluded.failures,window_start=excluded.window_start,"
            "locked_until=excluded.locked_until",
            (name, peer_ip, count, start, now + LOCK_SECONDS if count >= MAX_FAILED_ATTEMPTS else 0),
        )
    return None


def issue_auth_session(user_id: str, *, replace_token: str | None = None) -> tuple[str, str]:
    """Atomically replace this browser's prior cookie session when signing in again.

    Do not revoke independent devices/sessions. Revocation under the same writer
    lock prevents an old in-flight SSE stream from remaining authorized after an
    account switch. A failed issuance rolls back the replacement.
    """
    _schema()
    token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
    now = int(time.time())
    with _connect() as db:
        db.execute("BEGIN IMMEDIATE")
        user = db.execute("SELECT disabled FROM users WHERE id=?", (user_id,)).fetchone()
        if user is None or user["disabled"]:
            raise ValueError("Inactive user")
        if isinstance(replace_token, str) and 24 <= len(replace_token) <= 128:
            db.execute("UPDATE auth_sessions SET revoked_at=? "
                       "WHERE token_hash=? AND revoked_at IS NULL",
                       (now, _digest(replace_token)))
        db.execute("INSERT INTO auth_sessions(id,user_id,token_hash,csrf_secret,created_at,expires_at) "
                   "VALUES(?,?,?,?,?,?)",
                   (str(uuid4()), user_id, _digest(token), csrf, now, now + SESSION_TTL_SECONDS))
    return token, csrf


def principal_from_token(token: str | None) -> SecurityContext | None:
    if not isinstance(token, str) or not 24 <= len(token) <= 128:
        return None
    _schema()
    with _connect() as db:
        row = db.execute(
            "SELECT s.id AS session_id,s.user_id,s.expires_at,s.revoked_at,u.disabled,u.role "
            "FROM auth_sessions s JOIN users u ON u.id=s.user_id WHERE s.token_hash=?",
            (_digest(token),)).fetchone()
    if (row is None or row["disabled"] or row["revoked_at"] is not None
            or row["expires_at"] <= int(time.time())):
        return None
    return SecurityContext(user_id=str(row["user_id"]), role=row["role"],
                           auth_session_id=str(row["session_id"]))


def assert_active(principal: SecurityContext) -> None:
    _schema()
    with _connect() as db:
        row = db.execute(
            "SELECT s.expires_at,s.revoked_at,u.disabled,u.role FROM auth_sessions s "
            "JOIN users u ON u.id=s.user_id WHERE s.id=? AND s.user_id=?",
            (principal.auth_session_id, principal.user_id)).fetchone()
    if (row is None or row["revoked_at"] is not None or row["disabled"]
            or row["expires_at"] <= int(time.time()) or row["role"] != principal.role):
        raise PermissionError("Authentication required")


def revoke_session(principal: SecurityContext) -> None:
    _schema()
    with _connect() as db:
        db.execute("BEGIN IMMEDIATE")
        db.execute("UPDATE auth_sessions SET revoked_at=? "
                   "WHERE id=? AND user_id=? AND revoked_at IS NULL",
                   (int(time.time()), principal.auth_session_id, principal.user_id))


def csrf_for_principal(principal: SecurityContext) -> str:
    assert_active(principal)
    with _connect() as db:
        row = db.execute("SELECT csrf_secret FROM auth_sessions WHERE id=? AND user_id=?",
                         (principal.auth_session_id, principal.user_id)).fetchone()
    if row is None:
        raise PermissionError("Authentication required")
    return str(row["csrf_secret"])


def verify_csrf(principal: SecurityContext, csrf: str | None) -> bool:
    if not isinstance(csrf, str) or not 24 <= len(csrf) <= 128:
        return False
    try:
        actual = csrf_for_principal(principal)
    except PermissionError:
        return False
    return secrets.compare_digest(actual, csrf)


def safe_user(user_id: str) -> dict | None:
    _schema()
    with _connect() as db:
        row = db.execute("SELECT id,username,role,disabled FROM users WHERE id=?",
                         (user_id,)).fetchone()
    if not row or row["disabled"]:
        return None
    return {"user_id": str(row["id"]), "username": row["username"], "role": row["role"]}
