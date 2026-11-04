"""T06 Task 4: real Manager auth and one-time SQLite CAS, NOT graph resume."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from hashlib import sha256
import sqlite3
import threading

from fastapi.testclient import TestClient
import pytest

from retailiq.api import app
from retailiq.infrastructure import auth
from retailiq.infrastructure import sessions
from retailiq.infrastructure import uc01_proposals as persistence
from tests.auth_client import signed_in_client, active_principal
from tests.test_t06_proposals import candidate, committed_case
from tests.test_fiction_unified import fiction  # dependency of candidate fixture


def pending_submission(client, store):
    signed_in_client(app, client=client)
    sid = committed_case(client, store)
    created = client.post("/api/uc01/proposals", json={"session_id": sid})
    assert created.status_code == 201, created.text
    return created.json(), active_principal(client)


@pytest.mark.parametrize("decision,status", [
    ("approve", "APPROVED_LOCAL"), ("reject", "REJECTED_LOCAL"),
])
def test_manager_decides_once_and_analyst_sees_separate_status(candidate, decision, status):
    _, _, store = candidate
    with TestClient(app) as analyst, TestClient(app) as manager:
        proposal, owner = pending_submission(analyst, store)
        assert proposal["status"] == "PENDING"
        signed_in_client(app, client=manager, role="manager")
        reviewer = active_principal(manager)
        endpoint = f"/api/uc01/proposals/{proposal['proposal_id']}/decision"
        first = manager.post(endpoint, json={"decision": decision, "expected_version": 1})
        assert first.status_code == 200, first.text
        assert first.json()["status"] == status
        assert first.json()["version"] == 2
        assert first.json()["reviewed_by"] == reviewer.user_id
        assert first.json()["operational_write_executed"] is False
        assert manager.post(endpoint, json={"decision": decision, "expected_version": 1}).status_code == 409
        assert analyst.get("/api/uc01/my-proposals").json()["proposals"][0]["status"] == status
        assert analyst.get("/api/sessions/" + proposal["proposal_id"]).status_code == 404
        assert analyst.post(endpoint, json={"decision": "approve", "expected_version": 1,
                                           "role": "manager"}).status_code in (403, 422)


def test_two_managers_race_only_one_cas_winner(candidate):
    _, _, store = candidate
    with TestClient(app) as analyst, TestClient(app) as mgr_a, TestClient(app) as mgr_b:
        proposal, _ = pending_submission(analyst, store)
        signed_in_client(app, client=mgr_a, role="manager")
        signed_in_client(app, client=mgr_b, role="manager")
        url = f"/api/uc01/proposals/{proposal['proposal_id']}/decision"
        barrier = threading.Barrier(2)
        def attempt(client, decision):
            barrier.wait(timeout=15)
            return client.post(url, json={"decision": decision, "expected_version": 1})
        with ThreadPoolExecutor(max_workers=2) as pool:
            f1 = pool.submit(attempt, mgr_a, "approve")
            f2 = pool.submit(attempt, mgr_b, "reject")
            outcomes = [f1.result(timeout=30), f2.result(timeout=30)]
        assert sorted(x.status_code for x in outcomes) == [200, 409]
        recorded = analyst.get("/api/uc01/my-proposals").json()["proposals"][0]
        assert recorded["version"] == 2
        assert recorded["status"] in ("APPROVED_LOCAL", "REJECTED_LOCAL")


def test_expired_and_stale_version_refuse_decision(candidate):
    _, _, store = candidate
    with TestClient(app) as analyst, TestClient(app) as manager:
        proposal, _ = pending_submission(analyst, store)
        signed_in_client(app, client=manager, role="manager")
        url = f"/api/uc01/proposals/{proposal['proposal_id']}/decision"
        assert manager.post(url, json={"decision": "approve", "expected_version": 2}).status_code == 409
        with sqlite3.connect(sessions._path()) as db:
            db.execute("UPDATE uc01_proposals SET expires_at=0 WHERE proposal_id=?",
                       (proposal["proposal_id"],))
        assert manager.post(url, json={"decision": "approve", "expected_version": 1}).status_code == 409
        assert analyst.get("/api/uc01/my-proposals").json()["proposals"][0]["status"] != "APPROVED_LOCAL"


def test_revoked_manager_and_cross_session_identity_not_accepted(candidate):
    _, _, store = candidate
    with TestClient(app) as analyst, TestClient(app) as manager:
        proposal, _ = pending_submission(analyst, store)
        signed_in_client(app, client=manager, role="manager")
        principal = active_principal(manager)
        auth.revoke_session(principal)
        url = f"/api/uc01/proposals/{proposal['proposal_id']}/decision"
        assert manager.post(url, json={"decision": "approve", "expected_version": 1}).status_code == 401
        # The persistence CAS must also reject a retained-but-revoked backend principal.
        with pytest.raises(PermissionError):
            persistence.decide_proposal(proposal["proposal_id"], "approve", 1, principal,
                                        verified_snapshot=proposal)
        assert analyst.get("/api/uc01/my-proposals").json()["proposals"][0]["status"] == "PENDING"


def test_db_trigger_failure_rolls_back_and_fiction_bytes_unchanged(candidate):
    db, _, store = candidate
    before = sha256(db.read_bytes()).hexdigest()
    with TestClient(app) as analyst, TestClient(app) as manager:
        proposal, _ = pending_submission(analyst, store)
        signed_in_client(app, client=manager, role="manager")
        url = f"/api/uc01/proposals/{proposal['proposal_id']}/decision"
        with sqlite3.connect(sessions._path()) as conn:
            conn.execute("""CREATE TRIGGER abort_review BEFORE UPDATE ON uc01_proposals
                BEGIN SELECT RAISE(ABORT,'simulated transaction crash'); END""")
        response = manager.post(url, json={"decision": "approve", "expected_version": 1})
        assert response.status_code in (409, 500, 503)
        assert analyst.get("/api/uc01/my-proposals").json()["proposals"][0]["status"] == "PENDING"
        with sqlite3.connect(sessions._path()) as conn:
            conn.execute("DROP TRIGGER abort_review")
        good = manager.post(url, json={"decision": "approve", "expected_version": 1})
        assert good.status_code == 200, good.text
        assert sha256(db.read_bytes()).hexdigest() == before


def test_changed_source_rejected_even_if_snapshot_was_previously_verified(candidate):
    db, manifest, store = candidate
    with TestClient(app) as analyst, TestClient(app) as manager:
        proposal, _ = pending_submission(analyst, store)
        signed_in_client(app, client=manager, role="manager")
        # Tamper Fiction after proposal snapshot; no source update/rehash authorizes it.
        with sqlite3.connect(db) as conn:
            conn.execute("UPDATE inventory_snapshots_v2 SET on_hand=1 WHERE snapshot_id='SNAP-fixture'")
        url = f"/api/uc01/proposals/{proposal['proposal_id']}/decision"
        refused = manager.post(url, json={"decision": "approve", "expected_version": 1})
        assert refused.status_code in (409, 422), refused.text
        assert analyst.get("/api/uc01/my-proposals").json()["proposals"][0]["status"] == "PENDING"
