"""T02 contract/negative tests; intentionally OFFLINE, not an actual LLM run."""
from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pytest

from scripts.verify_uc01_live_release import (
    CASE, CUTOFF, DOCUMENT, POLICY, POLICY_SHA, RECEIVED,
    RELEASE, RELEASE_SHA, SNAPSHOT, OBSERVED, WAREHOUSE,
    check_live_result, independent_oracle,
)


@pytest.fixture
def passing_payload():
    sid, rid = "valid-test-session", "valid-test-request"
    oracle = {
        "case_id": CASE, "cutoff": CUTOFF, "order_id": "order-uuid",
        "order_item_id": "item-uuid", "product_id": "product-uuid",
        "warehouse_id": WAREHOUSE, "snapshot_id": SNAPSHOT,
        "available": 5, "requested": 1, "observed_at": OBSERVED,
        "received_at": RECEIVED, "policy_id": POLICY,
        "document_id": DOCUMENT, "policy_sha256": POLICY_SHA,
        "release_sha256": RELEASE_SHA, "release_version": RELEASE,
    }
    refs = [
        "fulfillment_cases/" + CASE,
        "inventory_snapshots_v2/" + SNAPSHOT,
        "fulfillment_policies/" + POLICY,
        "knowledge_documents/" + DOCUMENT,
        "orders/order-uuid", "order_items/item-uuid",
    ]
    result = {
        "request_id": rid, "session_id": sid, "intent": "backorder",
        "active_agent": "backorder_agent", "route_fallback": False,
        "disposition": "NEEDS_REVIEW", "approval_status": "NOT_REQUESTED",
        "as_of": CUTOFF, "temporal": {"evidence_cutoff": CUTOFF},
        "source": {"id": "fiction-retail/sqlite", "version": RELEASE,
                   "sha256": RELEASE_SHA},
        "records": [{"case_id": CASE, "cutoff": CUTOFF,
                     "warehouse_id": WAREHOUSE, "snapshot_id": SNAPSHOT,
                     "observed_at": OBSERVED, "received_at": RECEIVED,
                     "available_at_observation": 5}],
        "evidence_refs": refs,
        "findings": [{"text": "Verified observation",
                      "evidence_refs": ["inventory_snapshots_v2/" + SNAPSHOT,
                                        "knowledge_documents/" + DOCUMENT]}],
        "answer": "Alternative warehouse " + WAREHOUSE + " requires Manager review",
        "limitations": ["Historical evidence is not current inventory"],
        "capability_plan": {"case_id": CASE,
                            "capabilities": ["fiction.backorder.investigate"]},
    }
    calls = [{"case_id": CASE, "order_id": "order-uuid",
              "order_item_id": "item-uuid", "product_id": "product-uuid",
              "cutoff": CUTOFF, "policy_verified": True,
              "policy_id": POLICY, "document_id": DOCUMENT,
              "document_sha256": POLICY_SHA}]
    events = [
        {"request_id": rid, "session_id": sid, "event": "agent.routed",
         "agent": "backorder_agent", "route_fallback": False},
        {"request_id": rid, "session_id": sid, "event": "tool.sql.started"},
        {"request_id": rid, "session_id": sid, "event": "tool.sql.completed",
         "tool": "fiction.backorder.investigate"},
        {"request_id": rid, "session_id": sid, "event": "chat.turn_result"},
    ]
    return result, oracle, calls, events, rid, sid


def test_t02_oracle_check_accepts_complete_contract_offline(passing_payload):
    result, oracle, calls, events, rid, sid = passing_payload
    verified = check_live_result(result, oracle, calls, events, rid, sid)
    assert verified["disposition"] == "NEEDS_REVIEW"
    assert verified["evidence_refs_verified"] == 6


@pytest.mark.parametrize("corruption", [
    "provider_fallback", "wrong_cutoff", "wrong_source", "wrong_snapshot",
    "unverified_policy", "missing_lineage", "missing_tool_trace",
    "faked_mcp_trace", "wrong_session", "unauthorized_approval",
])
def test_t02_gate_rejects_unverified_providers_or_business_facts(passing_payload, corruption):
    result, oracle, calls, events, rid, sid = deepcopy(passing_payload)
    if corruption == "provider_fallback":
        result["route_fallback"] = True
    elif corruption == "wrong_cutoff":
        result["as_of"] = "2026-10-20T11:00:00Z"
    elif corruption == "wrong_source":
        result["source"]["sha256"] = "incorrect"
    elif corruption == "wrong_snapshot":
        result["records"][0]["snapshot_id"] = "foreign-snapshot"
    elif corruption == "unverified_policy":
        calls[0]["policy_verified"] = False
    elif corruption == "missing_lineage":
        result["evidence_refs"].remove("knowledge_documents/" + DOCUMENT)
    elif corruption == "missing_tool_trace":
        events = [e for e in events if e["event"] != "tool.sql.completed"]
    elif corruption == "faked_mcp_trace":
        events.append({"request_id": rid, "session_id": sid, "event": "mcp.tool.completed"})
    elif corruption == "wrong_session":
        events[0]["session_id"] = "other-session"
    elif corruption == "unauthorized_approval":
        result["approval_status"] = "APPROVED"
    with pytest.raises(AssertionError):
        check_live_result(result, oracle, calls, events, rid, sid)


def test_t02_rejects_an_unmaterialized_git_lfs_pointer(tmp_path: Path):
    db = tmp_path / "fiction.sqlite"
    db.write_text("version https://git-lfs.github.com/spec/v1\n", encoding="utf-8")
    with pytest.raises(AssertionError, match="LFS object size"):
        independent_oracle(db, tmp_path / "manifest.json",
                           tmp_path / "knowledge", tmp_path / "pinned.json")
