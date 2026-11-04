"""T06 G1: independent real Fiction release oracle and authenticated local HITL.

This verifier requires the published LFS SQLite. It never approves a Fiction
transfer and never calls a paid model: the compiled chat router is FAKE while
the source/domain/HTTP auth/proposal/Manager transaction are real.

Missing LFS/knowledge is NOT_RUN, not evidence of PASS.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
import os
from pathlib import Path
from secrets import token_urlsafe
import tempfile
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

from fastapi.testclient import TestClient

from scripts.verify_uc01_live_release import (
    independent_oracle, CASE, CUTOFF, SNAPSHOT, WAREHOUSE,
    RELEASE_SHA, POLICY, POLICY_SHA, DOCUMENT,
)


def _sha(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _check(value: bool, label: str) -> None:
    if not value:
        raise AssertionError(label)


def _sign_in(client: TestClient, role: str):
    """CLI-equivalent local provisioning, actual login/CSRF, no static secrets."""
    from retailiq.infrastructure import auth
    username = "t06_" + uuid4().hex[:20]
    password = token_urlsafe(32)
    user_id = auth.create_local_user(username, role, password)
    response = client.post(
        "/api/auth/login", headers={"Origin": "http://testserver"},
        json={"username": username, "password": password})
    _check(response.status_code == 200, "Real local login failed")
    me = client.get("/api/auth/me")
    _check(me.status_code == 200, "CSRF bootstrap failed")
    client.headers.update({
        "Origin": "http://testserver",
        "X-CSRF-Token": me.json()["csrf_token"],
    })
    return user_id


def verify_authenticated_hitl(db: Path, manifest: Path, knowledge: Path,
                              expected: dict) -> dict:
    """Real FastAPI requests with a fake-only intent router, isolated app DB."""
    from retailiq.api import app
    from retailiq.orchestration import week1_graph as graph
    from retailiq.api.uc01_proposals import _verified_store
    from retailiq.infrastructure import sessions

    class FakeIntentRouter:
        def with_structured_output(self, schema):
            return self

        def invoke(self, messages):
            return SimpleNamespace(intent="backorder")

    with tempfile.TemporaryDirectory(prefix="ri-t06-g1-") as tmp:
        root = Path(tmp)
        env = {
            "RETAILIQ_MODE": "full",
            "RETAILIQ_FICTION_DB": str(db),
            "RETAILIQ_FICTION_MANIFEST": str(manifest),
            "RETAILIQ_FICTION_KNOWLEDGE_ROOT": str(knowledge),
            "RETAILIQ_CHAT_DB": str(root / "local_application.sqlite"),
            "RETAILIQ_CHECKPOINT_DB": str(root / "checkpoints.sqlite"),
            "RETAILIQ_LOG_FILE": str(root / "events.jsonl"),
            "LANGSMITH_TRACING": "false",
        }
        with patch.dict(os.environ, env), patch.object(
            graph, "chat_model", lambda: FakeIntentRouter()
        ):
            graph.close_checkpoint_graph()
            graph._fiction_store_cached.cache_clear()
            _verified_store.cache_clear()
            try:
                with TestClient(app) as analyst, TestClient(app) as manager:
                    owner_id = _sign_in(analyst, "analyst")
                    session = analyst.post("/api/sessions", json={})
                    _check(session.status_code == 201, "Analyst session creation failed")
                    sid = session.json()["id"]
                    reply = analyst.post("/ask", json={
                        "session_id": sid,
                        "question": "Investigate backorder case " + expected["case_id"] +
                                    ": can another warehouse cover it at the recorded cutoff?",
                    })
                    _check(reply.status_code == 200, "Source-backed compiled graph failed")
                    observed = reply.json()
                    _check(observed.get("intent") == "backorder" and
                           observed.get("disposition") == "NEEDS_REVIEW" and
                           observed.get("approval_status") == "NOT_REQUESTED",
                           "Compiled graph did not produce a grounded review candidate")
                    binding = sessions.last_committed_case_binding(
                        sid, owner_user_id=owner_id)
                    _check(binding is not None and binding["case_id"] == CASE and
                           binding["cutoff"] == CUTOFF and
                           binding["source_sha256"] == RELEASE_SHA,
                           "Committed source/cutoff binding missing or untrusted")

                    eligible = analyst.get("/api/uc01/eligibility",
                                           params={"session_id": sid})
                    _check(eligible.status_code == 200 and
                           eligible.json().get("eligible") is True,
                           "Release-backed candidate eligibility failed")
                    candidate = eligible.json()["candidate"]
                    _check(candidate["warehouse_id"] == WAREHOUSE and
                           candidate["snapshot_id"] == SNAPSHOT and
                           candidate["available_units"] == 5 and
                           candidate["requested_units"] == expected["requested"] and
                           candidate["policy_id"] == POLICY and
                           candidate["policy_document_id"] == DOCUMENT and
                           candidate["policy_sha256"] == POLICY_SHA and
                           candidate["source_sha256"] == RELEASE_SHA,
                           "Proposal candidate disagrees with independent SQL oracle")
                    submitted = analyst.post("/api/uc01/proposals",
                                              json={"session_id": sid})
                    _check(submitted.status_code == 201,
                           "Analyst cannot submit verified proposal")
                    proposal = submitted.json()
                    _check(proposal["status"] == "PENDING" and
                           proposal["version"] == 1 and
                           proposal["snapshot_id"] == SNAPSHOT,
                           "Immutable proposal is not pending or source-bound")
                    duplicate = analyst.post("/api/uc01/proposals",
                                             json={"session_id": sid})
                    _check(duplicate.status_code == 200 and
                           duplicate.json()["proposal_id"] == proposal["proposal_id"],
                           "Identical proposal is not idempotent")

                    reviewer_id = _sign_in(manager, "manager")
                    inbox = manager.get("/api/uc01/proposals")
                    _check(inbox.status_code == 200 and
                           len(inbox.json()["proposals"]) == 1,
                           "Manager does not see one bounded proposal")
                    _check(manager.get("/api/sessions/" + sid).status_code == 404,
                           "Manager was granted the Analyst conversation")
                    url = "/api/uc01/proposals/" + proposal["proposal_id"] + "/decision"
                    missing_csrf = manager.post(
                        url, json={"decision": "approve", "expected_version": 1},
                        headers={"X-CSRF-Token": "forged"})
                    _check(missing_csrf.status_code == 403,
                           "Forged CSRF was accepted")
                    decided = manager.post(url, json={
                        "decision": "approve", "expected_version": 1})
                    _check(decided.status_code == 200 and
                           decided.json()["status"] == "APPROVED_LOCAL" and
                           decided.json()["version"] == 2 and
                           decided.json()["reviewed_by"] == reviewer_id and
                           decided.json()["operational_write_executed"] is False,
                           "Manager CAS decision was not single-use and attributable")
                    replay = manager.post(url, json={
                        "decision": "approve", "expected_version": 1})
                    _check(replay.status_code == 409, "Manager replay was accepted")
                    owned = analyst.get("/api/uc01/my-proposals")
                    _check(owned.status_code == 200 and
                           owned.json()["proposals"][0]["status"] == "APPROVED_LOCAL",
                           "Analyst cannot inspect durable local review status")
                    return {
                        "case_id": CASE, "cutoff": CUTOFF,
                        "source_sha256": RELEASE_SHA, "warehouse_id": WAREHOUSE,
                        "snapshot_id": SNAPSHOT, "available_units": 5,
                        "policy_id": POLICY, "status": "APPROVED_LOCAL",
                        "version": 2, "replay_http": replay.status_code,
                        "csrf_http": missing_csrf.status_code,
                        "manager_chat_http": 404,
                        "identity_mode": "local_authenticated_analyst_and_manager",
                        "router_mode": "FAKE_INTENT_ONLY_NO_LLM",
                        "operational_write_executed": False,
                    }
            finally:
                graph.close_checkpoint_graph()
                graph._fiction_store_cached.cache_clear()
                _verified_store.cache_clear()


def main() -> int:
    p = argparse.ArgumentParser(description="Real Fiction G1 T06 authenticated decision oracle")
    p.add_argument("--db", type=Path,
                   default=Path("data/fiction/fiction_retail.sqlite"))
    p.add_argument("--manifest", type=Path,
                   default=Path("data/fiction/manifest.json"))
    p.add_argument("--knowledge-root", type=Path,
                   default=Path("data/fiction/knowledge"))
    p.add_argument("--retailiq-manifest", type=Path,
                   default=Path("data/fiction/manifest.json"))
    p.add_argument("--out", type=Path,
                   default=Path("data/quality_reports/uc01_t06_g1.json"))
    args = p.parse_args()
    report: dict = {
        "mode": "PINNED_REAL_FICTION_G1_AUTH_HTTP_FAKE_ROUTER_NO_LLM",
        "status": "NOT_RUN", "case_id": CASE,
        "expected_source_sha256": RELEASE_SHA,
        "commit_sha": os.getenv("GITHUB_SHA", "local"),
    }
    required = [args.db, args.manifest, args.knowledge_root,
                args.retailiq_manifest]
    if not all(path.exists() for path in required):
        report["reason_code"] = "MISSING_RELEASE_OR_LFS"
        code = 2
    else:
        code = 1
        try:
            before = _sha(args.db)
            expected = independent_oracle(
                args.db, args.manifest, args.knowledge_root, args.retailiq_manifest)
            report["observed"] = verify_authenticated_hitl(
                args.db.resolve(), args.manifest.resolve(),
                args.knowledge_root.resolve(), expected)
            _check(_sha(args.db) == before == RELEASE_SHA,
                   "Fiction bytes changed during local HITL")
            report["status"] = "PASS"
            report["fiction_sha_before_after"] = RELEASE_SHA
            code = 0
        except Exception as exc:
            # Do not print or persist raw provider errors, prompts, secrets or PII.
            report["status"] = "FAIL"
            report["error_type"] = type(exc).__name__
            report["reason_code"] = "VERIFICATION_FAILED"
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
