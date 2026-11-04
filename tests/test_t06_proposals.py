"""T06 Task 3: grounded Fiction proposal boundaries using a sealed mini release.

FIXTURE ONLY: the independent published G1 release oracle is a separate gate.
"""
from __future__ import annotations

import ast
from pathlib import Path
import sqlite3

import pytest
from fastapi.testclient import TestClient

from retailiq.api import app
from retailiq.infrastructure import sessions
from retailiq.domain.fiction import FictionDataError
from tests.auth_client import signed_in_client, active_principal
from tests.test_fiction_unified import fiction, add_snapshot, reseal, C1, P1, W2


@pytest.fixture
def candidate(fiction, tmp_path, monkeypatch):
    db, manifest, store = fiction
    add_snapshot(db, "SNAP-fixture", W2, "2026-10-16T11:00:00Z",
                 "2026-10-16T11:05:00Z", on_hand=5, reserved=1)
    store = reseal(db, manifest)
    monkeypatch.setenv("RETAILIQ_FICTION_DB", str(db))
    monkeypatch.setenv("RETAILIQ_FICTION_MANIFEST", str(manifest))
    monkeypatch.setenv("RETAILIQ_FICTION_KNOWLEDGE_ROOT",
                       str(Path(__file__).resolve().parents[1] / "data/fiction/knowledge"))
    monkeypatch.setenv("RETAILIQ_CHAT_DB", str(tmp_path / "proposals.sqlite"))
    return db, manifest, store


def binding(store, *, cutoff="2026-10-16T12:00:00Z", source_sha=None,
            disposition="NEEDS_REVIEW"):
    return {"version": 1, "case_id": C1, "cutoff": cutoff,
            "source_id": "fiction-retail/sqlite",
            "source_version": store.release["pack_version"],
            "source_sha256": source_sha or store.release["runtime_sha256"],
            "case_ref": f"fulfillment_cases/{C1}",
            "disposition": disposition, "source_request_id": "fixture-request"}


def committed_case(api, store):
    principal = active_principal(api)
    result = api.post("/api/sessions", json={})
    assert result.status_code == 201, result.text
    sid = result.json()["id"]
    sessions.add_turn(sid, f"Investigate {C1}", {
        "intent": "backorder", "active_agent": "backorder_agent",
        "answer": "Source-confirmed historical candidate",
        "disposition": "NEEDS_REVIEW", "approval_status": "NOT_REQUESTED",
        "capability_plan": {"capabilities": ["fiction.backorder.investigate"], "case_id": C1},
        "temporal": {"evidence_cutoff": "2026-10-16T12:00:00Z"},
        "source": {"id": "fiction-retail/sqlite", "version": store.release["pack_version"],
                   "sha256": store.release["runtime_sha256"]},
        "evidence_refs": [f"fulfillment_cases/{C1}"],
        "request_id": "fixture-request",
    }, principal=principal)
    assert sessions.last_committed_case_binding(sid, owner_user_id=principal.user_id)
    return sid


def test_verified_candidate_exact_pinned_cutoff_policy_and_units(candidate):
    from retailiq.domain.uc01_review import verified_candidate
    _, _, store = candidate
    root = Path(__file__).resolve().parents[1] / "data/fiction/knowledge"
    actual = verified_candidate(store, root, binding(store), None)
    assert actual["case_id"] == C1
    assert actual["product_id"] == P1
    assert actual["snapshot_id"] == "SNAP-fixture"
    assert actual["warehouse_id"] == W2
    assert actual["cutoff"] == "2026-10-16T12:00:00Z"
    assert actual["requested_units"] == 2
    assert actual["available_units"] == 4
    assert actual["policy_id"] == "FR-WH-2026-10-04"
    assert actual["source_sha256"] == store.release["runtime_sha256"]
    assert "customer" not in str(actual).lower()


@pytest.mark.parametrize("override", [
    {"cutoff": "2026-10-16T13:00:00Z"},
    {"source_sha256": "0" * 64},
    {"disposition": "SUPPORTED"},
])
def test_changed_cutoff_source_or_disposition_cannot_submit(candidate, override):
    from retailiq.domain.uc01_review import verified_candidate
    _, _, store = candidate
    changed = {**binding(store), **override}
    with pytest.raises((FictionDataError, ValueError)):
        verified_candidate(store, Path(__file__).resolve().parents[1] / "data/fiction/knowledge",
                           changed, None)


def test_candidate_absent_and_snapshot_selector_fail_closed(candidate):
    from retailiq.domain.uc01_review import verified_candidate
    db, manifest, store = candidate
    root = Path(__file__).resolve().parents[1] / "data/fiction/knowledge"
    with pytest.raises(ValueError):
        verified_candidate(store, root, binding(store), "SNAP-unverified")
    with sqlite3.connect(db) as conn:
        conn.execute("UPDATE inventory_snapshots_v2 SET on_hand=1 WHERE snapshot_id='SNAP-fixture'")
    no_stock_store = reseal(db, manifest)
    with pytest.raises(ValueError):
        verified_candidate(no_stock_store, root, binding(no_stock_store), None)


def test_multiple_candidates_require_explicit_snapshot(candidate):
    from retailiq.domain.uc01_review import verified_candidate
    db, manifest, store = candidate
    root = Path(__file__).resolve().parents[1] / "data/fiction/knowledge"
    # Additional eligible alternative warehouse is a distinct recorded route.
    warehouse = "88888888-8888-4888-8888-888888888888"
    with sqlite3.connect(db) as conn:
        conn.execute("INSERT INTO warehouse_eligibility VALUES (?,?,?,?)",
                     (C1, warehouse, 1, "ALLOWED"))
        conn.execute("INSERT INTO inventory_snapshots_v2 VALUES(?,?,?,?,?,?,?,?)",
                     ("SNAP-second", C1, P1, warehouse,
                      "2026-10-16T11:00:00Z", "2026-10-16T11:05:00Z", 8, 1))
    store = reseal(db, manifest)
    with pytest.raises(ValueError):
        verified_candidate(store, root, binding(store), None)
    chosen = verified_candidate(store, root, binding(store), "SNAP-second")
    assert chosen["warehouse_id"] == warehouse


def test_authenticated_submit_idempotent_and_manager_inbox_no_chat(candidate):
    db, manifest, store = candidate
    with TestClient(app) as api:
        signed_in_client(app, client=api)
        sid = committed_case(api, store)
        eligibility = api.get("/api/uc01/eligibility", params={"session_id": sid})
        assert eligibility.status_code == 200, eligibility.text
        assert eligibility.json()["eligible"] is True
        first = api.post("/api/uc01/proposals", json={"session_id": sid})
        assert first.status_code == 201, first.text
        proposal = first.json()
        assert proposal["status"] == "PENDING" and proposal["version"] == 1
        assert proposal["source_sha256"] == store.release["runtime_sha256"]
        again = api.post("/api/uc01/proposals", json={"session_id": sid})
        assert again.status_code == 200, again.text
        assert again.json()["proposal_id"] == proposal["proposal_id"]
        own = api.get("/api/uc01/my-proposals")
        assert [v["proposal_id"] for v in own.json()["proposals"]] == [proposal["proposal_id"]]
        # Manager has no access to Analyst chat but sees bounded review evidence.
        signed_in_client(app, client=api, role="manager")
        inbox = api.get("/api/uc01/proposals")
        assert inbox.status_code == 200, inbox.text
        assert len(inbox.json()["proposals"]) == 1
        details = api.get("/api/uc01/proposals/" + proposal["proposal_id"])
        assert details.status_code == 200
        assert "Source-confirmed historical candidate" not in str(details.json())
        assert "messages" not in str(details.json()).lower()
        assert api.get("/api/sessions/" + sid).status_code == 404


def test_different_analyst_same_case_conflicts_and_manager_cannot_submit(candidate):
    _, _, store = candidate
    with TestClient(app) as api:
        signed_in_client(app, client=api)
        sid = committed_case(api, store)
        original = api.post("/api/uc01/proposals", json={"session_id": sid})
        assert original.status_code == 201, original.text
        signed_in_client(app, client=api)
        other_sid = committed_case(api, store)
        second = api.post("/api/uc01/proposals", json={"session_id": other_sid})
        assert second.status_code == 409
        assert original.json()["proposal_id"] not in second.text
        assert api.get("/api/uc01/my-proposals").json()["proposals"] == []
        signed_in_client(app, client=api, role="manager")
        denied = api.post("/api/uc01/proposals", json={"session_id": other_sid})
        assert denied.status_code in (403, 404)


def test_review_domain_cannot_import_orchestration():
    p = Path(__file__).resolve().parents[1] / "retailiq/domain/uc01_review.py"
    tree = ast.parse(p.read_text(encoding="utf-8"))
    names = [node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)]
    assert not any(name and "orchestration" in name for name in names)
