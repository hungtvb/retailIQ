"""Authenticated UC-01 proposal API. Manager cannot see Analyst conversations."""
from __future__ import annotations

from functools import lru_cache
import os
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field

from retailiq.api.auth import _principal
from retailiq.domain.fiction import FictionDataError, FictionStore
from retailiq.domain.uc01_review import verified_candidate
from retailiq.infrastructure import auth
from retailiq.infrastructure.sessions import (
    get_session, last_committed_case_binding, session_mutation, SessionBusyError,
)
from retailiq.infrastructure.uc01_proposals import (
    ProposalConflict, submit_proposal, my_proposals, manager_inbox, manager_proposal,
)

router = APIRouter(prefix="/api/uc01", tags=["uc01-local-review"])


class SubmitProposal(BaseModel):
    model_config = ConfigDict(extra="forbid")
    session_id: str = Field(min_length=36, max_length=36)
    candidate_snapshot_id: str | None = Field(default=None, min_length=5, max_length=80)


def _source_paths() -> tuple[str, str, str]:
    root = Path(__file__).resolve().parents[2]
    return (
        os.getenv("RETAILIQ_FICTION_DB") or str(root / "data/fiction/fiction_retail.sqlite"),
        os.getenv("RETAILIQ_FICTION_MANIFEST") or str(root / "data/fiction/manifest.json"),
        os.getenv("RETAILIQ_FICTION_KNOWLEDGE_ROOT") or str(root / "data/fiction/knowledge"),
    )


@lru_cache(maxsize=2)
def _verified_store(db: str, manifest: str) -> FictionStore:
    # Hash/verify release once per immutable runtime path, never per HTTP read.
    # Store._q also detects file replacement and unverified WAL sidecars.
    return FictionStore.open(db, manifest)


def _owned_binding(session_id: str, principal) -> dict:
    if get_session(session_id, owner_user_id=principal.user_id,
                   include_messages=False) is None:
        raise HTTPException(status_code=404, detail="Session not found")
    binding = last_committed_case_binding(session_id, owner_user_id=principal.user_id)
    if binding is None or binding.get("disposition") != "NEEDS_REVIEW":
        raise HTTPException(status_code=422, detail="Committed eligible case context is required")
    return binding


def _candidate(binding: dict, snapshot_id: str | None) -> dict:
    db, manifest, knowledge = _source_paths()
    try:
        return verified_candidate(_verified_store(db, manifest),
                                  Path(knowledge), binding, snapshot_id)
    except FictionDataError:
        # No unverified source, release or policy information is returned.
        raise HTTPException(status_code=422,
                            detail="Historical source, policy or cutoff is not verified") from None
    except (OSError, FileNotFoundError):
        raise HTTPException(status_code=503,
                            detail="Pinned Fiction release is unavailable") from None
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from None


@router.get("/eligibility")
def eligibility(session_id: str, request: Request):
    principal = _principal(request)
    if principal.role != "analyst":
        raise HTTPException(status_code=403, detail="Analyst access required")
    auth.assert_active(principal)
    if get_session(session_id, owner_user_id=principal.user_id,
                   include_messages=False) is None:
        raise HTTPException(status_code=404, detail="Session not found")
    binding = last_committed_case_binding(session_id, owner_user_id=principal.user_id)
    if binding is None or binding.get("disposition") != "NEEDS_REVIEW":
        return {"eligible": False, "reason_codes": ["NO_COMMITTED_ELIGIBLE_CASE"]}
    try:
        canonical = _candidate(binding, None)
    except HTTPException as error:
        return {"eligible": False,
                "reason_codes": ["VERIFICATION_FAILED" if error.status_code == 422 else
                                 "SOURCE_UNAVAILABLE"]}
    return {"eligible": True, "reason_codes": [],
            "candidate": canonical, "local_review_only": True}


@router.post("/proposals", status_code=201)
def submit(data: SubmitProposal, request: Request, response: Response):
    principal = _principal(request)
    if principal.role != "analyst":
        raise HTTPException(status_code=403, detail="Analyst access required")
    auth.assert_active(principal)
    try:
        with session_mutation(data.session_id):
            binding = _owned_binding(data.session_id, principal)
            canonical = _candidate(binding, data.candidate_snapshot_id)
            proposal, created = submit_proposal(principal, data.session_id,
                                                binding, canonical)
        response.status_code = 201 if created else 200
        return proposal
    except ProposalConflict:
        raise HTTPException(status_code=409,
                            detail="Historical case review cycle is unavailable") from None
    except PermissionError:
        raise HTTPException(status_code=401, detail="Authentication required") from None
    except SessionBusyError:
        raise HTTPException(status_code=409, detail="Session currently processing a turn") from None
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid reviewed case evidence") from None


@router.get("/my-proposals")
def my_submissions(request: Request):
    principal = _principal(request)
    if principal.role != "analyst":
        raise HTTPException(status_code=403, detail="Analyst access required")
    auth.assert_active(principal)
    return {"proposals": my_proposals(principal)}


@router.get("/proposals")
def pending_manager_reviews(request: Request):
    principal = _principal(request)
    if principal.role != "manager":
        raise HTTPException(status_code=403, detail="Manager access required")
    auth.assert_active(principal)
    return {"proposals": manager_inbox(principal)}


@router.get("/proposals/{proposal_id}")
def manager_review_detail(proposal_id: str, request: Request):
    principal = _principal(request)
    if principal.role != "manager":
        raise HTTPException(status_code=403, detail="Manager access required")
    auth.assert_active(principal)
    item = manager_proposal(principal, proposal_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Proposal not found")
    return item
