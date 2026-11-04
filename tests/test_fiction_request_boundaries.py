"""R1-A: scope extraction must retain graph, HTTP, and security behavior.

These are focused offline compatibility/negative tests. They do not claim a
provider, actual Fiction release, or real MCP transport was exercised.
"""
from __future__ import annotations

import pytest

from retailiq.api import http
from retailiq.orchestration import fiction_requests as fiction
from retailiq.orchestration import week1_graph as graph


SKU = "FR-0123456789ABCDEF"
WAREHOUSE = "55555555-5555-4555-8555-555555555555"
CASE = "CASE-ABCDEF12-1234-4567-89AB-ABCDEF123456"


def test_original_graph_and_http_exception_identity_is_preserved():
    assert graph.InvalidCaseId is fiction.InvalidCaseId is http.InvalidCaseId
    assert graph.InvalidFictionScope is fiction.InvalidFictionScope is http.InvalidFictionScope
    assert graph.UnresolvedCaseReference is fiction.UnresolvedCaseReference
    assert issubclass(fiction.InvalidFictionScope, fiction.InvalidCaseId)
    assert issubclass(fiction.UnresolvedCaseReference, fiction.InvalidCaseId)


def test_original_graph_parsing_entrypoints_remain_shared_objects():
    assert graph._fiction_inventory_request is fiction._fiction_inventory_request
    assert graph._uc01_followup_kind is fiction._uc01_followup_kind
    assert graph._case_id_for_uc01 is fiction._case_id_for_uc01


def test_stock_parser_preserves_canonical_identity_and_explicit_warehouse():
    assert fiction._fiction_inventory_request(f"stock for {SKU}") == (SKU, None)
    assert fiction._fiction_inventory_request(
        f"Tồn kho {SKU} tại kho {WAREHOUSE}"
    ) == (SKU, WAREHOUSE)
    assert fiction._fiction_inventory_request(f"Show the catalog product {SKU}") is None


@pytest.mark.parametrize("question,reason", [
    (f"stock {SKU} now", "UNSUPPORTED_TEMPORAL_SCOPE"),
    (f"stock {SKU} as of 2026-10-21", "UNSUPPORTED_TEMPORAL_SCOPE"),
    (f"tồn kho {SKU} hiện tại", "UNSUPPORTED_TEMPORAL_SCOPE"),
    (f"stock {SKU} and sales", "MULTI_INTENT_UNSUPPORTED"),
    (f"stock {SKU} compare revenue", "MULTI_INTENT_UNSUPPORTED"),
    (f"stock {SKU} FR-ABCDEF0123456789", "Exactly one complete FR-SKU"),
    (f"stock FR-abc", "Exactly one complete FR-SKU"),
    (f"stock {SKU} {WAREHOUSE}", "Specify at most one explicitly labeled"),
])
def test_invalid_fiction_stock_scope_fails_closed(question, reason):
    with pytest.raises(fiction.InvalidFictionScope, match=reason):
        fiction._fiction_inventory_request(question)


def test_explicit_case_id_normalization_and_ambiguous_cases():
    assert fiction._case_id_for_uc01(f"Investigate {CASE}") == CASE.lower().replace("case-", "CASE-", 1)
    with pytest.raises(fiction.InvalidCaseId, match="exactly one"):
        fiction._case_id_for_uc01("Investigate CASE-not-a-uuid")
    with pytest.raises(fiction.InvalidCaseId, match="exactly one"):
        fiction._case_id_for_uc01(f"Compare {CASE} and {CASE}")


@pytest.mark.parametrize("question,kind", [
    ("kho thứ hai?", "ambiguous_warehouse"),
    ("Chính sách nào áp dụng?", "policy"),
    ("Vì sao cần Manager phê duyệt?", "policy"),
    ("Chính sách yêu cầu gì khi snapshot quá 24 giờ?", "policy"),
    ("What does the policy require for a snapshot older than 24 hours?", "policy"),
    ("Đơn này gồm sản phẩm nào?", "order_details"),
    ("What is this order delivery status at cutoff?", "order_status_at_cutoff"),
    ("Other warehouses?", "alternatives"),
    ("Chính sách giá nào?", None),
    ("What is the refund policy?", None),
    (f"Investigate {CASE}", None),
])
def test_committed_case_followup_grammar_stays_conservative(question, kind):
    assert fiction._uc01_followup_kind(question) == kind


def test_graph_router_still_uses_local_fiction_scope_patch_seam(monkeypatch):
    monkeypatch.setattr(graph, "_fiction_inventory_request", lambda _q: (SKU, None))
    command = graph.route({"question": "An intentionally unrecognized string", "history": []})
    assert command.goto == "fiction_inventory_agent"
    assert command.update["fiction_product"] == SKU
    assert command.update["route_fallback"] is False


def test_graph_router_still_refuses_uncommitted_case_followup(monkeypatch):
    monkeypatch.setattr(graph, "_fiction_inventory_request", lambda _q: None)
    monkeypatch.setattr(graph, "_uc01_followup_kind", lambda _q: "policy")
    with pytest.raises(fiction.UnresolvedCaseReference, match="committed case reference"):
        graph.route({"question": "policy?", "history": [], "verified_case_context": None})
