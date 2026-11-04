"""R1-B: fact-to-result helpers stay read-only and preserve lineage.

Pure offline negative/compatibility checks; real MCP and provider behavior are
verified separately by compiled-graph/API and published-release CI.
"""
from __future__ import annotations

import pytest

from retailiq.orchestration.fiction_handlers import inventory_update, backorder_update
from retailiq.orchestration.fiction_requests import UnresolvedCaseReference


CASE_ID = "CASE-11111111-1111-4111-8111-111111111111"
ORDER_ID = "22222222-2222-4222-8222-222222222222"
ITEM_ID = "33333333-3333-4333-8333-333333333333"
PRODUCT_ID = "44444444-4444-4444-8444-444444444444"
WAREHOUSE_ID = "55555555-5555-4555-8555-555555555555"
SNAP_ID = "SNAP-verified"
CUTOFF = "2026-10-21T11:00:00Z"
CAPABILITY = "fiction.backorder.investigate"


def _investigation():
    return {
        "data": {
            "cutoff": CUTOFF,
            "case": {
                "case_id": CASE_ID, "order_id": ORDER_ID,
                "order_item_id": ITEM_ID, "product_id": PRODUCT_ID,
                "request_qty": 1,
            },
            "evidence_candidates": [{
                "snapshot_id": SNAP_ID, "warehouse_id": WAREHOUSE_ID,
                "available_at_observation": 5,
            }],
            "snapshots": [{
                "snapshot_id": SNAP_ID,
                "observed_at": "2026-10-21T10:00:00Z",
                "received_at": "2026-10-21T10:05:00Z",
            }],
            "policy": {
                "applicable_at_cutoff": True,
                "policy_id": "FR-WH-2026-10-04",
                "document_id": "DOC-verified",
            },
        },
        "source": {"id": "fiction", "version": "unified-v1", "sha256": "verified"},
        "temporal": {"evidence_cutoff": CUTOFF},
        "record_refs": [f"fulfillment_cases/{CASE_ID}"],
        "reason_codes": [],
        "disposition": "NEEDS_REVIEW",
        "approval_status": "NOT_REQUESTED",
        "limitations": ["CASE_SCOPED_ONLY"],
    }


def _deny_order(_order_id):
    raise AssertionError("Unexpected Order MCP call on a non-order follow-up")


def test_inventory_response_keeps_undated_scope_and_missing_is_not_zero():
    state = {"question": "stock of product", "fiction_product": "FR-0123456789ABCDEF"}
    result = {
        "data": [], "limitations": ["NO_INVENTORY_RECORDS"],
        "source": {"id": "verified"}, "record_refs": [], "temporal": {},
    }
    output = inventory_update(state, result)
    assert output["intent"] == "fiction_stock"
    assert output["active_agent"] == "fiction_inventory_agent"
    assert "Missing evidence is not zero" in output["answer"]
    assert output["limitations"] == result["limitations"]
    assert output["source"] is result["source"]
    assert output["evidence_refs"] == []
    assert output["approval_status"] is None


def test_inventory_record_is_not_mislabeled_current():
    state = {"question": "stock of product", "fiction_product": "FR-0123456789ABCDEF"}
    result = {
        "data": [{"warehouse_id": WAREHOUSE_ID, "available_snapshot": 5}],
        "limitations": ["UNDATED_INVENTORY"], "source": {"id": "verified"},
        "record_refs": ["inventory/ref"], "temporal": {"observed_at": None},
    }
    output = inventory_update(state, result)
    assert WAREHOUSE_ID in output["answer"]
    assert "does NOT prove current or historical stock" in output["answer"]
    assert output["records"] == result["data"]
    assert output["evidence_refs"] == ["inventory/ref"]


@pytest.mark.parametrize("kind", [None, "policy", "alternatives", "order_status_at_cutoff"])
def test_case_response_uses_only_verified_sql_without_ghost_mcp(kind):
    output = backorder_update(
        {"question": "Explain the verified backorder"}, _investigation(),
        CASE_ID, followup=kind, committed=None,
        read_order=_deny_order, capability=CAPABILITY,
    )
    assert output["capability_plan"]["capabilities"] == [CAPABILITY]
    assert output["active_agent"] == "backorder_agent"
    assert output["source"]["sha256"] == "verified"
    assert output["approval_status"] == "NOT_REQUESTED"
    assert output["findings"]
    if kind == "order_status_at_cutoff":
        assert output["disposition"] == "INSUFFICIENT_EVIDENCE"
        assert "ORDER_STATUS_AT_CUTOFF_UNVERIFIED" in output["reason_codes"]


def test_order_details_scope_mismatch_rejected_after_single_observed_lookup():
    calls = []

    def wrong_source(order_id):
        calls.append(order_id)
        return {
            "source": {"id": "untrusted"},
            "scope": {"order_id": ORDER_ID},
            "data": {"lines": [{
                "order_item_id": ITEM_ID, "product_id": PRODUCT_ID,
                "quantity": 1,
            }]},
            "record_refs": ["orders/untrusted"],
        }

    with pytest.raises(UnresolvedCaseReference, match="Order/case identity or source"):
        backorder_update(
            {"question": "Details of this order"}, _investigation(), CASE_ID,
            followup="order_details",
            committed={"source_request_id": "verified-turn"},
            read_order=wrong_source, capability=CAPABILITY,
        )
    assert calls == [ORDER_ID]
