"""Immutable, one-cycle UC-01 review proposals in the application SQLite only.

Not Fiction persistence, and not the legacy simulated workflow manager gate.
"""
from __future__ import annotations

from hashlib import sha256
import json
from sqlite3 import IntegrityError
import time
from uuid import uuid4

from retailiq.infrastructure.sessions import (
    _connect, _assert_owned_active_in_transaction, _valid_case_binding,
)
from retailiq.security import SecurityContext


REVIEW_TTL_SECONDS = 24 * 60 * 60


class ProposalConflict(ValueError):
    """A review cycle already exists for this historical case/release/cutoff."""


def _schema() -> None:
    with _connect() as db:
        db.executescript("""
            CREATE TABLE IF NOT EXISTS uc01_proposals (
              proposal_id TEXT PRIMARY KEY,
              owner_user_id TEXT NOT NULL REFERENCES users(id),
              session_id TEXT NOT NULL,
              case_id TEXT NOT NULL,
              source_sha256 TEXT NOT NULL,
              cutoff TEXT NOT NULL,
              snapshot_json TEXT NOT NULL,
              snapshot_fingerprint TEXT NOT NULL,
              status TEXT NOT NULL CHECK(status IN
                ('PENDING','APPROVED_LOCAL','REJECTED_LOCAL','EXPIRED','INVALIDATED')),
              version INTEGER NOT NULL CHECK(version >= 1),
              submitted_at INTEGER NOT NULL,
              expires_at INTEGER NOT NULL,
              reviewed_by TEXT,
              reviewed_at INTEGER,
              UNIQUE(case_id,source_sha256,cutoff)
            );
            CREATE INDEX IF NOT EXISTS ix_uc01_proposals_owner
              ON uc01_proposals(owner_user_id,submitted_at);
            CREATE INDEX IF NOT EXISTS ix_uc01_proposals_status
              ON uc01_proposals(status,submitted_at);
        """)


def _fingerprint(canonical: dict) -> tuple[str, str]:
    if not isinstance(canonical, dict):
        raise ValueError("Verified canonical snapshot required")
    raw = json.dumps(canonical, ensure_ascii=False, sort_keys=True,
                     separators=(",", ":"), allow_nan=False)
    if len(raw) > 16_000:
        raise ValueError("Proposal evidence exceeds limit")
    return raw, sha256(raw.encode("utf-8")).hexdigest()


def _view(row, *, manager: bool = False) -> dict:
    item = json.loads(row["snapshot_json"])
    item.pop("source_request_id", None)
    item.update({
        "proposal_id": row["proposal_id"],
        # Historical expiry is a derived effective state, even if no writer
        # has yet materialized an EXPIRED transition in application SQLite.
        "status": ("EXPIRED" if row["status"] == "PENDING" and
                   row["expires_at"] <= int(time.time()) else row["status"]),
        "version": row["version"],
        "submitted_at": row["submitted_at"],
        "expires_at": row["expires_at"],
        "reviewed_at": row["reviewed_at"],
        "reviewed_by": row["reviewed_by"],
        "local_decision_only": True,
        "operational_write_executed": False,
    })
    # No raw Analyst session/chat/memory/trace/checkpoint in Manager review.
    if not manager:
        item["owner_user_id"] = row["owner_user_id"]
    return item


def _latest_binding(db, session_id: str, owner_id: str) -> dict | None:
    row = db.execute("""SELECT m.intent,m.agent,m.evidence_json FROM messages m
        JOIN sessions s ON s.id=m.session_id
        WHERE m.session_id=? AND s.owner_user_id=? AND m.role='assistant'
        ORDER BY m.id DESC LIMIT 1""", (session_id, owner_id)).fetchone()
    if not row or row["intent"] != "backorder" or row["agent"] != "backorder_agent":
        return None
    try:
        payload = json.loads(row["evidence_json"])
        binding = payload.get("case_binding")
        return binding if _valid_case_binding(binding) else None
    except (ValueError, TypeError, AttributeError):
        return None


def submit_proposal(principal: SecurityContext, session_id: str,
                    binding: dict, canonical: dict) -> tuple[dict, bool]:
    if principal.role != "analyst":
        raise PermissionError("Only Analysts submit proposals")
    raw, fingerprint = _fingerprint(canonical)
    if (not _valid_case_binding(binding)
            or binding.get("disposition") != "NEEDS_REVIEW"
            or any(canonical.get(dst) != binding.get(src) for dst, src in (
                ("case_id", "case_id"), ("source_sha256", "source_sha256"),
                ("cutoff", "cutoff"), ("source_id", "source_id"),
                ("source_version", "source_version")))):
        raise ValueError("Canonical proposal does not match committed case evidence")
    _schema()
    now = int(time.time())
    with _connect() as db:
        db.execute("BEGIN IMMEDIATE")
        _assert_owned_active_in_transaction(db, session_id, principal)
        if _latest_binding(db, session_id, principal.user_id) != binding:
            raise ProposalConflict("Committed case evidence changed before submission")
        old = db.execute("""SELECT * FROM uc01_proposals WHERE case_id=?
            AND source_sha256=? AND cutoff=?""",
            (canonical["case_id"], canonical["source_sha256"],
             canonical["cutoff"])).fetchone()
        if old:
            if (old["owner_user_id"] == principal.user_id
                    and old["snapshot_fingerprint"] == fingerprint
                    and old["status"] == "PENDING"
                    and old["expires_at"] > now):
                return _view(old), False
            raise ProposalConflict("Historical case review cycle is unavailable")
        proposal_id = str(uuid4())
        db.execute("""INSERT INTO uc01_proposals
            (proposal_id,owner_user_id,session_id,case_id,source_sha256,cutoff,
             snapshot_json,snapshot_fingerprint,status,version,submitted_at,expires_at)
            VALUES (?,?,?,?,?,?,?,?, 'PENDING',1,?,?)""",
            (proposal_id, principal.user_id, session_id, canonical["case_id"],
             canonical["source_sha256"], canonical["cutoff"], raw, fingerprint,
             now, now + REVIEW_TTL_SECONDS))
        created = db.execute(
            "SELECT * FROM uc01_proposals WHERE proposal_id=?", (proposal_id,)
        ).fetchone()
        return _view(created), True


def my_proposals(principal: SecurityContext) -> list[dict]:
    if principal.role != "analyst":
        raise PermissionError("Only Analysts have submitted proposals")
    _schema()
    with _connect() as db:
        rows = db.execute("""SELECT * FROM uc01_proposals
            WHERE owner_user_id=? ORDER BY submitted_at DESC,proposal_id DESC LIMIT 100""",
            (principal.user_id,)).fetchall()
    return [_view(row) for row in rows]


def manager_inbox(principal: SecurityContext) -> list[dict]:
    if principal.role != "manager":
        raise PermissionError("Manager access required")
    _schema()
    with _connect() as db:
        rows = db.execute("""SELECT * FROM uc01_proposals
            WHERE status='PENDING' AND expires_at>?
            ORDER BY submitted_at DESC,proposal_id DESC LIMIT 100""",
            (int(time.time()),)).fetchall()
    return [_view(row, manager=True) for row in rows]


def manager_proposal(principal: SecurityContext, proposal_id: str) -> dict | None:
    if principal.role != "manager":
        raise PermissionError("Manager access required")
    _schema()
    with _connect() as db:
        row = db.execute("SELECT * FROM uc01_proposals WHERE proposal_id=?",
                         (proposal_id,)).fetchone()
    return _view(row, manager=True) if row else None


def snapshot_for_manager(principal: SecurityContext, proposal_id: str) -> dict | None:
    """Private reread for verifying the immutable source; no chat access."""
    if principal.role != "manager":
        raise PermissionError("Manager access required")
    _schema()
    with _connect() as db:
        row = db.execute(
            "SELECT owner_user_id,snapshot_json FROM uc01_proposals WHERE proposal_id=?",
            (proposal_id,)).fetchone()
    if row is None:
        return None
    if row["owner_user_id"] == principal.user_id:
        raise PermissionError("Submitter cannot review their own proposal")
    return json.loads(row["snapshot_json"])


def decide_proposal(proposal_id: str, decision: str, expected_version: int,
                    reviewer: SecurityContext, *, verified_snapshot: dict) -> dict:
    """Single-writer local decision with auth, ownership, source fingerprint and CAS.

    Caller supplies server-recomputed verified facts, never a browser snapshot.
    The app SQLite transaction serializes revocation, both Manager reviewers
    and the decision row; Fiction database remains read-only.
    """
    if reviewer.role != "manager":
        raise PermissionError("Manager access required")
    if decision not in ("approve", "reject"):
        raise ValueError("Invalid decision")
    if type(expected_version) is not int or expected_version < 1:
        raise ValueError("Positive expected_version required")
    _, fingerprint = _fingerprint(verified_snapshot)
    target = "APPROVED_LOCAL" if decision == "approve" else "REJECTED_LOCAL"
    _schema()
    now = int(time.time())
    with _connect() as db:
        db.execute("BEGIN IMMEDIATE")
        active = db.execute("""SELECT 1 FROM auth_sessions a
            JOIN users u ON u.id=a.user_id
            WHERE a.id=? AND a.user_id=? AND u.role='manager'
              AND u.disabled=0 AND a.revoked_at IS NULL AND a.expires_at>?""",
            (reviewer.auth_session_id, reviewer.user_id, now)).fetchone()
        if active is None:
            raise PermissionError("Manager authentication revoked")
        row = db.execute(
            "SELECT * FROM uc01_proposals WHERE proposal_id=?", (proposal_id,)
        ).fetchone()
        if row is None:
            raise KeyError("Proposal not found")
        if row["owner_user_id"] == reviewer.user_id:
            raise PermissionError("Self review is forbidden")
        if (row["status"] != "PENDING"
                or row["expires_at"] <= now
                or row["version"] != expected_version
                or row["snapshot_fingerprint"] != fingerprint):
            raise ProposalConflict("Stale, expired or changed historical proposal")
        changed = db.execute("""UPDATE uc01_proposals
            SET status=?,version=version+1,reviewed_by=?,reviewed_at=?
            WHERE proposal_id=? AND status='PENDING'
              AND version=? AND expires_at>?""",
            (target, reviewer.user_id, now, proposal_id, expected_version, now))
        if changed.rowcount != 1:
            raise ProposalConflict("Concurrent Manager decision conflict")
        committed = db.execute(
            "SELECT * FROM uc01_proposals WHERE proposal_id=?", (proposal_id,)
        ).fetchone()
        return _view(committed, manager=True)
