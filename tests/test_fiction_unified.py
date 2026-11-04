"""Focused Fiction M0 contract and adversarial business scenarios.

These tests construct a valid, small 27-table release and use FictionStore.open,
not an unverified constructor. The real uploaded SQLite is audited separately.
"""
from __future__ import annotations

import json
import shutil
from hashlib import sha256
import sqlite3
from pathlib import Path
import subprocess
import sys

import pytest

from retailiq.domain.fiction import FictionStore, FictionDataError, _period, verify_release
from retailiq.domain.backorder import investigate_backorder
from retailiq.infrastructure.sqlite import query

P1 = "11111111-1111-4111-8111-111111111111"
P2 = "22222222-2222-4222-8222-222222222222"
O1 = "33333333-3333-4333-8333-333333333333"
R1 = "44444444-4444-4444-8444-444444444444"
W1 = "55555555-5555-4555-8555-555555555555"  # assigned warehouse
W2 = "77777777-7777-4777-8777-777777777777"  # alternative warehouse
I1 = "66666666-6666-4666-8666-666666666666"
C1 = "CASE-77777777-7777-4777-8777-777777777777"


def reseal(db_path: Path, manifest_path: Path) -> FictionStore:
    """Recreate the mini-release manifest after deliberate fixture edits."""
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    with sqlite3.connect(db_path) as conn:
        manifest["table_counts"] = {
            table: conn.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
            for table in manifest["table_counts"]
        }
    manifest["runtime_sha256"] = sha256(db_path.read_bytes()).hexdigest()
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    return FictionStore.open(db_path, manifest_path)


@pytest.fixture
def fiction(tmp_path):
    path = tmp_path / "fiction.sqlite"
    manifest_path = tmp_path / "manifest.json"
    with sqlite3.connect(path) as c:
        c.executescript('''
        CREATE TABLE products(product_id TEXT, sku TEXT, name TEXT, category TEXT, brand TEXT, price REAL);
        CREATE TABLE orders(order_id TEXT, customer_id TEXT, order_date TEXT, order_status TEXT, total_amount REAL);
        CREATE TABLE order_items(order_item_id TEXT, order_id TEXT, product_id TEXT, quantity INT, unit_price REAL, discount_pct INT);
        CREATE TABLE shipments(shipment_id TEXT, order_id TEXT, warehouse_id TEXT, shipped_date TEXT, delivered_date TEXT, shipment_state TEXT);
        CREATE TABLE inventory(inventory_id TEXT, product_id TEXT, warehouse_id TEXT, quantity_on_hand INT, reserved_quantity INT, last_restocked_date TEXT);
        CREATE TABLE warehouses(warehouse_id TEXT, name TEXT);
        CREATE TABLE returns(return_id TEXT, order_id TEXT, product_id TEXT, return_date TEXT, refund_amount REAL, return_reason_code TEXT);
        CREATE TABLE fulfillment_cases(case_id TEXT, order_id TEXT, order_item_id TEXT, product_id TEXT, request_qty INT, assigned_warehouse_id TEXT, case_date TEXT);
        CREATE TABLE operational_events(event_id TEXT, case_id TEXT, event_type TEXT, occurred_at TEXT, recorded_at TEXT);
        CREATE TABLE inventory_snapshots_v2(snapshot_id TEXT, case_id TEXT, product_id TEXT, warehouse_id TEXT, observed_at TEXT, received_at TEXT, on_hand INT, reserved INT);
        CREATE TABLE warehouse_eligibility(case_id TEXT, warehouse_id TEXT, eligible INT, reason_code TEXT);
        CREATE TABLE fulfillment_policies(policy_id TEXT, policy_summary TEXT, requires_manager_approval INT, provenance TEXT);
        CREATE TABLE knowledge_documents(document_id TEXT, product_id TEXT, policy_id TEXT, kind TEXT, relative_path TEXT, sha256 TEXT, provenance TEXT);
        CREATE TABLE metadata(key TEXT PRIMARY KEY, value TEXT);
        ''')
        # Mirror the final schema's 27 named business tables. Empty unrelated
        # tables are sufficient for release gate tests; no fake production rows.
        manifest = json.loads((Path(__file__).resolve().parents[1] / "data/fiction/manifest.json").read_text())
        for table in manifest["table_counts"]:
            if table not in {"products", "orders", "order_items", "shipments", "inventory",
                             "returns", "fulfillment_cases", "operational_events",
                             "inventory_snapshots_v2", "warehouse_eligibility", "metadata",
                              "fulfillment_policies", "knowledge_documents", "warehouses"}:
                c.execute(f'CREATE TABLE "{table}" (dummy TEXT)')
        sku = lambda pid: "FR-" + sha256(pid.encode()).hexdigest()[:16].upper()
        c.executemany('INSERT INTO products VALUES(?,?,?,?,?,?)',
                      [(P1, sku(P1), "Device", "electronics", "Brand", 20.0),
                       (P2, sku(P2), "Other", "electronics", "Brand", 25.0)])
        c.execute("INSERT INTO orders VALUES (?,?,?,?,?)", (O1, "CUSTOMER_SECRET", "2026-10-15", "delivered", 20.0))
        c.execute("INSERT INTO order_items VALUES (?,?,?,?,?,?)", (I1, O1, P1, 2, 10.0, 0))
        c.executemany("INSERT INTO warehouses VALUES (?,?)", [(W1, "Assigned"), (W2, "Alternative")])
        c.execute("INSERT INTO inventory VALUES (?,?,?,?,?,?)", (I1, P1, W1, 4, 1, "2026-10-01"))
        c.execute("INSERT INTO returns VALUES (?,?,?,?,?,?)", (R1, O1, P1, "2026-10-18", 30.0, "DAMAGED"))
        c.execute("INSERT INTO fulfillment_cases VALUES (?,?,?,?,?,?,?)", (C1, O1, I1, P1, 2, W1, "2026-10-16"))
        c.execute("INSERT INTO operational_events VALUES (?,?,?,?,?)",
                  ("event1", C1, "evidence_cutoff_reached", "2026-10-16T12:00:00Z", "2026-10-16T12:01:00Z"))
        c.executemany("INSERT INTO warehouse_eligibility VALUES (?,?,?,?)",
                      [(C1, W1, 1, "ALLOWED"), (C1, W2, 1, "ALLOWED")])
        policy_path = Path(__file__).resolve().parents[1] / "data/fiction/knowledge/policies/FR-WH-2026-10-04.md"
        c.execute("INSERT INTO fulfillment_policies VALUES (?,?,?,?)",
                  ("FR-WH-2026-10-04", "Warehouse transfer policy", 1, "scenario_generated"))
        c.execute("INSERT INTO knowledge_documents VALUES (?,?,?,?,?,?,?)",
                  ("DOC-test-warehouse-policy", None, "FR-WH-2026-10-04", "business_policy",
                   "policies/FR-WH-2026-10-04.md", sha256(policy_path.read_bytes()).hexdigest(),
                   "scenario_generated"))
        manifest["content_sha256"] = "mini-release-fixture-content"
        manifest["dataset_business_as_of"] = "2026-11-03T00:00:00+07:00"
        c.executemany("INSERT INTO metadata VALUES (?,?)", [
            ("version", "fiction-retail-unified-v1.0.0"),
            ("dataset_business_as_of", manifest["dataset_business_as_of"]),
            ("output_checksum", manifest["content_sha256"]),
        ])
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    return path, manifest_path, reseal(path, manifest_path)


def add_snapshot(path, sid, warehouse, observed, received, *, on_hand=5, reserved=1):
    with sqlite3.connect(path) as conn:
        conn.execute("INSERT INTO inventory_snapshots_v2 VALUES(?,?,?,?,?,?,?,?)",
                     (sid, C1, P1, warehouse, observed, received, on_hand, reserved))


def test_verified_release_identity_and_nonpii(fiction):
    path, manifest, store = fiction
    sku = "FR-" + sha256(P1.encode()).hexdigest()[:16].upper()
    assert store.resolve_product(sku) == P1
    assert store.product(sku)["data"]["product_id"] == P1
    assert store.resolve_product(P2) == P2
    assert store.inventory(P1)["data"][0]["available_snapshot"] == 3
    assert "UNDATED_INVENTORY" in store.inventory(P1)["limitations"][0]
    assert store.inventory(P2)["data"] == []
    assert "NO_INVENTORY_RECORDS" in store.inventory(P2)["limitations"][1]
    assert "CUSTOMER_SECRET" not in str(store.order(O1))
    ranked = store.top_sellers("2026-10")
    assert ranked["data"][0]["delivered_units"] == 2
    assert ranked["data"][0]["contributing_order_lines"] == 1
    assert ranked["aggregate_evidence"]["source_tables"] == ["orders", "order_items", "products"]
    assert ranked["aggregate_evidence"]["record_refs_role"] == "product_identity_only"
    assert "PARTIAL_OR_FUTURE_PERIOD" in " ".join(store.top_sellers("2026-11")["limitations"])
    assert verify_release(path, manifest)["product_count"] == 2


def test_refund_missing_and_invalid_source_arithmetic(fiction):
    path, manifest, store = fiction
    result = store.refund(R1)
    assert result["data"]["refund_above_order_value"] is True
    assert result["data"]["refund_above_returned_product_lines"] is True
    assert result["data"]["returned_product_lines_net_usd"] == "20.00"
    assert "not evidence of approved" in result["limitations"][0]
    with sqlite3.connect(path) as conn:
        conn.execute("UPDATE order_items SET discount_pct=150 WHERE order_item_id=?", (I1,))
    with pytest.raises(FictionDataError, match="changed since release"):
        store.refund(R1)  # verified snapshot cannot be silently changed
    store = reseal(path, manifest)
    with pytest.raises(FictionDataError, match="discount"):
        store.refund(R1)
    with sqlite3.connect(path) as conn:
        conn.execute("DELETE FROM order_items WHERE order_item_id=?", (I1,))
    store = reseal(path, manifest)
    result = store.refund(R1)
    assert result["data"]["returned_product_lines_net_usd"] is None
    assert result["data"]["refund_above_returned_product_lines"] is None
    assert any("NO_MATCHING_ORDER_LINE" in reason for reason in result["limitations"])


def test_transfer_requires_alternative_and_marks_temporal_rejections(fiction):
    path, manifest, store = fiction
    assert "NO_CASE_SNAPSHOT" in store.fulfillment_case(C1)["limitations"]
    add_snapshot(path, "assigned", W1, "2026-10-16T11:00:00Z", "2026-10-16T11:05:00Z")
    add_snapshot(path, "stale", W2, "2026-10-15T10:00:00Z", "2026-10-15T10:05:00Z")
    store = reseal(path, manifest)
    result = store.fulfillment_case(C1)
    assert not result["data"]["evidence_candidates"]
    reasons = {s["snapshot_id"]: s["exclusion_reasons"] for s in result["data"]["snapshots"]}
    assert "ASSIGNED_WAREHOUSE_NOT_ALTERNATIVE" in reasons["assigned"]
    assert "STALE_OBSERVATION" in reasons["stale"]
    assert f"warehouse_eligibility/{C1}/{W2}" in result["record_refs"]

    add_snapshot(path, "positive", W2, "2026-10-16T11:00:00Z", "2026-10-16T11:05:00Z")
    add_snapshot(path, "late", W2, "2026-10-16T11:30:00Z", "2026-10-16T12:30:00Z", on_hand=9)
    store = reseal(path, manifest)
    result = store.fulfillment_case(C1)
    assert [r["snapshot_id"] for r in result["data"]["evidence_candidates"]] == ["positive"]
    reasons = {s["snapshot_id"]: s["exclusion_reasons"] for s in result["data"]["snapshots"]}
    assert "RECEIVED_AFTER_CUTOFF" in reasons["late"]
    assert "SUPERSEDED_BY_NEWER_OBSERVATION" in reasons["stale"]

    add_snapshot(path, "newer", W2, "2026-10-16T11:40:00Z", "2026-10-16T11:45:00Z", on_hand=0, reserved=0)
    store = reseal(path, manifest)
    result = store.fulfillment_case(C1)
    assert not result["data"]["evidence_candidates"]
    reasons = {s["snapshot_id"]: s["exclusion_reasons"] for s in result["data"]["snapshots"]}
    assert "INSUFFICIENT_AVAILABLE" in reasons["newer"]
    assert "SUPERSEDED_BY_NEWER_OBSERVATION" in reasons["positive"]


def test_fail_closed_release_gate_and_readonly(fiction, tmp_path):
    path, manifest, store = fiction
    with pytest.raises(FictionDataError, match="Use FictionStore.open"):
        FictionStore(path, dict(store.release))  # no public unverified constructor
    with pytest.raises(ValueError): store.resolve_product("EL-001")
    with pytest.raises(ValueError): store.order("NOT-AN-ORDER")
    with pytest.raises(ValueError): store.top_sellers("2026-13")
    with pytest.raises(ValueError): store.top_sellers("2026-10", 0)
    with pytest.raises(ValueError): query("DELETE FROM products", db_path=path)
    with pytest.raises(sqlite3.OperationalError): query("SELECT * FROM non_existing_table", db_path=path)
    with pytest.raises(FictionDataError): verify_release(path, tmp_path / "missing.json")
    tampered = json.loads(manifest.read_text())
    tampered["runtime_sha256"] = "0" * 64
    manifest.write_text(json.dumps(tampered), encoding="utf-8")
    with pytest.raises(FictionDataError, match="binary SHA-256"):
        FictionStore.open(path, manifest)


def test_cli_checks_survive_python_optimized_mode():
    from scripts.verify_fiction_runtime import _check
    with pytest.raises(FictionDataError, match="injected failure"):
        _check(False, "injected failure")
    script = "from scripts.verify_fiction_runtime import _check; _check(False, 'injected failure')"
    proc = subprocess.run([sys.executable, "-O", "-c", script], capture_output=True, text=True)
    assert proc.returncode != 0
    assert "injected failure" in proc.stderr


def test_period_bounds():
    assert _period("2026-12") == ("2026-12-01", "2027-01-01")


def test_inventory_unknown_identity_is_not_missing_stock(fiction):
    _, _, store = fiction
    # Known product with no rows is distinct from an unknown product identifier.
    existing = store.inventory(P2)
    assert existing["scope"]["product_id"] == P2
    assert any("NO_INVENTORY_RECORDS" in reason for reason in existing["limitations"])

    for unknown in ("00000000-0000-4000-8000-000000000000", "FR-AAAAAAAAAAAAAAAA"):
        missing = store.inventory(unknown)
        assert missing["data"] == []
        assert missing["scope"]["requested_product"] == unknown
        assert missing["scope"]["product_id"] is None
        assert missing["limitations"] == ["PRODUCT_NOT_FOUND"]
        assert missing["record_refs"] == []


def test_verified_snapshot_rejects_wal_journal_even_after_resealing(fiction):
    path, manifest, _ = fiction
    # A valid checksum of the primary .sqlite is insufficient for WAL-mode DBs.
    writer = sqlite3.connect(path)
    try:
        assert writer.execute("PRAGMA journal_mode=WAL").fetchone()[0] == "wal"
    finally:
        writer.close()
    with pytest.raises(FictionDataError, match="DELETE journal mode|WAL sidecar"):
        reseal(path, manifest)


def test_verified_store_fails_closed_on_late_wal_sidecar(fiction):
    path, manifest, store = fiction
    sidecar = path.with_name(path.name + "-wal")
    try:
        sidecar.write_bytes(b"unverified WAL data")
        with pytest.raises(FictionDataError, match="WAL sidecar"):
            store.product(P1)
    finally:
        sidecar.unlink(missing_ok=True)
    assert store.product(P1)["data"]["product_id"] == P1
    # The release gate also refuses even a pre-existing empty WAL sidecar.
    try:
        sidecar.touch()
        with pytest.raises(FictionDataError, match="WAL sidecar"):
            FictionStore.open(path, manifest)
    finally:
        sidecar.unlink(missing_ok=True)

def _copy_policy(tmp_path):
    root = tmp_path / "knowledge"
    (root / "policies").mkdir(parents=True, exist_ok=True)
    source = Path(__file__).resolve().parents[1] / "data/fiction/knowledge/policies/FR-WH-2026-10-04.md"
    shutil.copyfile(source, root / "policies/FR-WH-2026-10-04.md")
    return root


def test_uc01_m1_candidate_and_scoped_negative_and_missing_evidence(fiction, tmp_path):
    path, manifest, store = fiction
    root = _copy_policy(tmp_path)

    missing = investigate_backorder(store, C1, knowledge_root=root)
    assert missing["disposition"] == "INSUFFICIENT_EVIDENCE"
    assert "NO_CASE_SNAPSHOT" in missing["reason_codes"]
    assert missing["approval_status"] == "NOT_REQUESTED"
    assert missing["data"]["policy"]["applicable_at_cutoff"] is True

    add_snapshot(path, "recent-alternative", W2, "2026-10-16T11:00:00Z",
                 "2026-10-16T11:05:00Z", on_hand=5, reserved=1)
    store = reseal(path, manifest)
    candidate = investigate_backorder(store, C1, knowledge_root=root)
    assert candidate["disposition"] == "NEEDS_REVIEW"
    assert candidate["reason_codes"] == []
    assert candidate["data"]["evidence_candidates"][0]["snapshot_id"] == "recent-alternative"
    assert candidate["data"]["evidence_candidates"][0]["available_at_observation"] == 4
    assert f"knowledge_documents/DOC-test-warehouse-policy" in candidate["record_refs"]
    assert candidate["scope"]["finding_scope"] == "recorded_case_alternative_warehouses_only"

    with sqlite3.connect(path) as conn:
        conn.execute("UPDATE inventory_snapshots_v2 SET on_hand=1, reserved=0 WHERE snapshot_id='recent-alternative'")
    store = reseal(path, manifest)
    negative = investigate_backorder(store, C1, knowledge_root=root)
    assert negative["disposition"] == "SUPPORTED"
    assert negative["data"]["evidence_candidates"] == []
    assert negative["data"]["snapshots"][0]["exclusion_reasons"] == ["INSUFFICIENT_AVAILABLE"]


def test_uc01_m1_policy_cutoff_and_missing_source_fail_closed(fiction, tmp_path):
    path, manifest, _ = fiction
    root = _copy_policy(tmp_path)
    add_snapshot(path, "good", W2, "2026-10-16T11:00:00Z", "2026-10-16T11:01:00Z")
    store = reseal(path, manifest)

    policy_file = root / "policies/FR-WH-2026-10-04.md"
    policy_file.unlink()
    missing = investigate_backorder(store, C1, knowledge_root=root)
    assert missing["disposition"] == "INSUFFICIENT_EVIDENCE"
    assert missing["reason_codes"] == ["POLICY_DOCUMENT_MISSING"]

    root = _copy_policy(tmp_path)
    policy_file.write_bytes(policy_file.read_bytes() + b"\n# tampered")
    with pytest.raises(FictionDataError, match="SHA-256 mismatch"):
        investigate_backorder(store, C1, knowledge_root=root)

    root = _copy_policy(tmp_path)
    with sqlite3.connect(path) as conn:
        conn.execute("UPDATE operational_events SET occurred_at='2026-11-03T00:00:00Z' WHERE case_id=?", (C1,))
    store = reseal(path, manifest)
    expired = investigate_backorder(store, C1, knowledge_root=root)
    assert expired["disposition"] == "INSUFFICIENT_EVIDENCE"
    assert "POLICY_NOT_EFFECTIVE_AT_CUTOFF" in expired["reason_codes"]


def test_uc01_m1_stale_evidence_and_bad_case_join(fiction, tmp_path):
    path, manifest, _ = fiction
    root = _copy_policy(tmp_path)
    add_snapshot(path, "stale", W2, "2026-10-15T10:00:00Z",
                 "2026-10-15T10:05:00Z", on_hand=50)
    store = reseal(path, manifest)
    stale = investigate_backorder(store, C1, knowledge_root=root)
    assert stale["disposition"] == "INSUFFICIENT_EVIDENCE"
    assert "NO_USABLE_SNAPSHOT_FOR_ELIGIBLE_ROUTE" in stale["reason_codes"]
    assert "STALE_OBSERVATION" in stale["data"]["snapshots"][0]["exclusion_reasons"]

    with sqlite3.connect(path) as conn:
        conn.execute("UPDATE fulfillment_cases SET order_item_id=? WHERE case_id=?",
                     ("00000000-0000-4000-8000-000000000000", C1))
    store = reseal(path, manifest)
    with pytest.raises(FictionDataError, match="mismatch"):
        investigate_backorder(store, C1, knowledge_root=root)


def test_uc01_policy_document_copy_is_exact_pinned_release_bytes():
    source = Path(__file__).resolve().parents[1] / "data/fiction/knowledge/policies/FR-WH-2026-10-04.md"
    assert sha256(source.read_bytes()).hexdigest() == "f3ff7463e67e034360fd87b35c1c71286445be0de1431009591821489bd4d9c8"


def test_uc01_one_verified_candidate_does_not_require_every_route_snapshot(fiction, tmp_path):
    path, manifest, _ = fiction
    root = _copy_policy(tmp_path)
    add_snapshot(path, "good", W2, "2026-10-16T11:00:00Z", "2026-10-16T11:05:00Z")
    with sqlite3.connect(path) as conn:
        conn.execute("INSERT INTO warehouse_eligibility VALUES (?,?,?,?)",
                     (C1, "99999999-9999-4999-8999-999999999999", 1, "ALLOWED"))
    store = reseal(path, manifest)
    result = investigate_backorder(store, C1, knowledge_root=root)
    assert result["disposition"] == "NEEDS_REVIEW"
    assert "NO_USABLE_SNAPSHOT_FOR_ELIGIBLE_ROUTE" in result["reason_codes"]
    assert [c["snapshot_id"] for c in result["data"]["evidence_candidates"]] == ["good"]


def test_uc01_untrusted_competing_policy_requires_authority_review(fiction, tmp_path):
    path, manifest, _ = fiction
    root = _copy_policy(tmp_path)
    add_snapshot(path, "good", W2, "2026-10-16T11:00:00Z",
                 "2026-10-16T11:05:00Z", on_hand=5, reserved=1)
    # Controlled adversarial fixture, NOT a case in published Fiction v1.
    with sqlite3.connect(path) as conn:
        conn.execute("INSERT INTO fulfillment_policies VALUES (?,?,?,?)",
                     ("FR-WH-UNREVIEWED", "Conflicting warehouse authority", 1,
                      "fixture_only"))
    store = reseal(path, manifest)
    result = investigate_backorder(store, C1, knowledge_root=root)
    assert result["data"]["evidence_candidates"]
    assert result["data"]["policy"] is None
    assert result["reason_codes"] == ["POLICY_CONFLICT"]
    assert result["disposition"] == "NEEDS_REVIEW"  # Policy review, NOT transfer.
    assert result["approval_status"] == "NOT_REQUESTED"



def test_uc01_t02_explicit_case_langgraph_api_with_real_fixture(monkeypatch, fiction, tmp_path):
    """Compiled LangGraph + actual FastAPI /ask; fake *router provider*, real SQL fixture."""
    from types import SimpleNamespace
    from fastapi.testclient import TestClient
from tests.auth_client import signed_in_client
    from retailiq.api import app
    from retailiq.orchestration import week1_graph as graph

    pytest.importorskip("langgraph")
    path, manifest, store = fiction
    root = _copy_policy(tmp_path)
    add_snapshot(path, "candidate", W2, "2026-10-16T11:00:00Z",
                 "2026-10-16T11:05:00Z")
    store = reseal(path, manifest)
    graph.close_checkpoint_graph()
    graph._fiction_store_cached.cache_clear()

    class RouterModel:
        def with_structured_output(self, schema):
            return self
        def invoke(self, messages):
            return SimpleNamespace(intent=graph.classify(messages[-1][1]))

    monkeypatch.setenv("RETAILIQ_MODE", "full")
    monkeypatch.setenv("RETAILIQ_FICTION_DB", str(path))
    monkeypatch.setenv("RETAILIQ_FICTION_MANIFEST", str(manifest))
    monkeypatch.setenv("RETAILIQ_FICTION_KNOWLEDGE_ROOT", str(root))
    monkeypatch.setenv("RETAILIQ_CHAT_DB", str(tmp_path / "sessions.sqlite3"))
    monkeypatch.setenv("RETAILIQ_CHECKPOINT_DB", str(tmp_path / "checkpoints.sqlite3"))
    monkeypatch.setenv("LANGSMITH_TRACING", "false")
    monkeypatch.setattr(graph, "chat_model", lambda: RouterModel())
    try:
        with TestClient(app) as client:
            signed_in_client(app, client=client)
            direct = graph.run(f"Investigate backorder {C1}")
            assert direct["disposition"] == "NEEDS_REVIEW"
            result = client.post("/ask", json={"question": f"Investigate backorder {C1}"})
            assert result.status_code == 200, result.text[:300]
            body = result.json()
            assert body["intent"] == "backorder"
            assert body["active_agent"] == "backorder_agent"
            assert body["mode"] == "LangGraph + Fiction verified SQL"
            assert body["disposition"] == "NEEDS_REVIEW"
            assert body["approval_status"] == "NOT_REQUESTED"
            assert body["as_of"] == "2026-10-16T12:00:00Z"
            assert body["records"][0]["warehouse_id"] == W2
            assert body["records"][0]["snapshot_id"] == "candidate"
            assert body["records"][0]["observed_at"] == "2026-10-16T11:00:00Z"
            assert "received at 2026-10-16T11:05:00Z" in body["findings"][0]["text"]
            assert body["source"]["sha256"] == store.release["runtime_sha256"]
            assert f"inventory_snapshots_v2/candidate" in body["evidence_refs"]
            assert body["capability_plan"]["capabilities"] == ["fiction.backorder.investigate"]
    finally:
        graph.close_checkpoint_graph()
        graph._fiction_store_cached.cache_clear()


def test_uc01_t02_rejects_ambiguous_or_invalid_case_without_tool_call(monkeypatch):
    from retailiq.orchestration import week1_graph as graph
    with pytest.raises(ValueError, match="exactly one"):
        graph._case_id_for_uc01("Investigate CASE-not-a-uuid")
    with pytest.raises(ValueError, match="exactly one"):
        graph._case_id_for_uc01(f"Compare {C1} and CASE-11111111-1111-4111-8111-111111111111")
    assert graph.classify(f"Backorder {C1}") == "backorder"



@pytest.mark.skipif(__import__("os").getenv("RETAILIQ_UC01_LIVE") != "true",
                    reason="Explicit paid provider-backed CI suite only")
def test_uc01_t02_live_provider_route_with_verified_sql_fixture(monkeypatch, fiction, tmp_path):
    """REAL LLM router + compiled LangGraph + Fiction fixture SQL; not real-release E2E."""
    from fastapi.testclient import TestClient
    from retailiq.api import app
    from retailiq.orchestration import week1_graph as graph
    from retailiq.domain import backorder as backorder_domain

    pytest.importorskip("langgraph")
    path, manifest, store = fiction
    root = _copy_policy(tmp_path)
    add_snapshot(path, "candidate", W2, "2026-10-16T11:00:00Z",
                 "2026-10-16T11:05:00Z")
    store = reseal(path, manifest)
    graph.close_checkpoint_graph()
    graph._fiction_store_cached.cache_clear()

    monkeypatch.setenv("RETAILIQ_MODE", "full")
    monkeypatch.setenv("RETAILIQ_FICTION_DB", str(path))
    monkeypatch.setenv("RETAILIQ_FICTION_MANIFEST", str(manifest))
    monkeypatch.setenv("RETAILIQ_FICTION_KNOWLEDGE_ROOT", str(root))
    monkeypatch.setenv("RETAILIQ_CHAT_DB", str(tmp_path / "sessions.sqlite3"))
    monkeypatch.setenv("RETAILIQ_CHECKPOINT_DB", str(tmp_path / "checkpoints.sqlite3"))
    actual_model = graph.chat_model
    actual_domain = backorder_domain.investigate_backorder
    provider_calls = []
    tool_inputs = []

    def provider():
        provider_calls.append("actual_provider_model_created")
        return actual_model()

    def tool(store, case_id, *, knowledge_root):
        tool_inputs.append({"case_id": case_id, "knowledge_root": str(knowledge_root)})
        return actual_domain(store, case_id, knowledge_root=knowledge_root)

    monkeypatch.setattr(graph, "chat_model", provider)
    monkeypatch.setattr(backorder_domain, "investigate_backorder", tool)
    try:
        with TestClient(app) as client:
            signed_in_client(app, client=client)
            response = client.post("/ask", json={"question": f"Investigate the backorder {C1}"})
            assert response.status_code == 200, response.text[:300]
            result = response.json()
            assert provider_calls == ["actual_provider_model_created"]
            assert tool_inputs == [{"case_id": C1, "knowledge_root": str(root)}]
            assert result["intent"] == "backorder"
            assert result["route_fallback"] is False, "Live provider disagreed or fell back"
            assert result["disposition"] == "NEEDS_REVIEW"
            assert result["approval_status"] == "NOT_REQUESTED"
            assert result["records"][0]["snapshot_id"] == "candidate"
            assert result["records"][0]["warehouse_id"] == W2
            assert result["source"]["sha256"] == store.release["runtime_sha256"]
            assert f"inventory_snapshots_v2/candidate" in result["evidence_refs"]
            assert "observed at 2026-10-16T11:00:00Z" in result["findings"][0]["text"]
    finally:
        graph.close_checkpoint_graph()
        graph._fiction_store_cached.cache_clear()



def test_uc01_t02_partial_candidate_finding_without_applicable_policy(monkeypatch, fiction, tmp_path):
    """Missing/conflicting policy must not crash graph or imply approved transfer."""
    from retailiq.orchestration import week1_graph as graph
    pytest.importorskip("langgraph")
    path, manifest, store = fiction
    root = _copy_policy(tmp_path)
    add_snapshot(path, "candidate", W2, "2026-10-16T11:00:00Z",
                 "2026-10-16T11:05:00Z")
    store = reseal(path, manifest)
    monkeypatch.setattr(graph, "_uc01_inputs", lambda: ("fixture-db", "fixture-manifest", str(root)))
    monkeypatch.setattr(graph, "_fiction_store_cached", lambda *_: store)
    (root / "policies/FR-WH-2026-10-04.md").unlink()

    partial = graph.backorder_agent({"question": f"Investigate {C1}"}).update
    assert partial["disposition"] == "INSUFFICIENT_EVIDENCE"
    assert partial["reason_codes"] == ["POLICY_DOCUMENT_MISSING"]
    assert partial["approval_status"] == "NOT_REQUESTED"
    assert "knowledge_documents/" not in str(partial["findings"])

    _copy_policy(tmp_path)
    with sqlite3.connect(path) as conn:
        conn.execute("INSERT INTO fulfillment_policies VALUES (?,?,?,?)",
                     ("FR-WH-UNREVIEWED", "Conflicting authority", 1, "fixture_only"))
    store = reseal(path, manifest)
    conflicting = graph.backorder_agent({"question": f"Investigate {C1}"}).update
    assert conflicting["disposition"] == "NEEDS_REVIEW"
    assert conflicting["reason_codes"] == ["POLICY_CONFLICT"]
    assert conflicting["approval_status"] == "NOT_REQUESTED"
    assert "knowledge_documents/" not in str(conflicting["findings"])



def test_uc01_t02_rejects_invalid_case_before_llm_and_sql(monkeypatch, tmp_path):
    """Invalid input is a client error, never a provider/configuration failure."""
    from fastapi.testclient import TestClient
    from retailiq.api import app
    from retailiq.orchestration import week1_graph as graph

    pytest.importorskip("langgraph")
    graph.close_checkpoint_graph()
    monkeypatch.setenv("RETAILIQ_MODE", "full")
    monkeypatch.setenv("RETAILIQ_CHAT_DB", str(tmp_path / "sessions.sqlite3"))
    monkeypatch.setenv("RETAILIQ_CHECKPOINT_DB", str(tmp_path / "checkpoints.sqlite3"))
    monkeypatch.setenv("LANGSMITH_TRACING", "false")
    invocations = []

    def unexpected_model():
        invocations.append("model")
        raise AssertionError("Invalid case ID must not reach the model")

    def unexpected_db(*args):
        invocations.append("db")
        raise AssertionError("Invalid case ID must not reach the database")

    monkeypatch.setattr(graph, "chat_model", unexpected_model)
    monkeypatch.setattr(graph, "_fiction_store_cached", unexpected_db)
    valid = C1.lower()
    assert graph._case_id_for_uc01(f"Investigate {valid}") == C1
    questions = [
        "Investigate CASE-not-a-uuid",
        f"Compare {C1} and CASE-11111111-1111-4111-8111-111111111111",
    ]
    try:
        with TestClient(app) as client:
            signed_in_client(app, client=client)
            for question in questions:
                response = client.post("/ask", json={"question": question})
                assert response.status_code == 422, response.text
                assert "exactly one explicit" in response.json()["detail"]
            assert invocations == []
    finally:
        graph.close_checkpoint_graph()



def test_uc01_api_does_not_misreport_internal_key_error_as_missing_session(monkeypatch):
    """Internal business/source errors must never become a spurious session 404."""
    from fastapi.testclient import TestClient
    from retailiq.api import app
    from retailiq.api import http

    def invalid_domain(*args, **kwargs):
        raise KeyError("unrelated business evidence key missing")

    monkeypatch.setattr(http, "ask", invalid_domain)
    with TestClient(app) as client:
        signed_in_client(app, client=client)
        response = client.post("/ask", json={"question": "Investigate business evidence"})
        assert response.status_code == 503
        assert "Session not found" not in response.text



def _uc01_context_client(monkeypatch, tmp_path, fiction, *, with_candidate=False):
    """Actual compiled Graph + HTTP, fake *router model*, real verified SQL fixture."""
    from types import SimpleNamespace
    from retailiq.orchestration import week1_graph as graph

    path, manifest, store = fiction
    if with_candidate:
        add_snapshot(path, "candidate", W2, "2026-10-16T11:00:00Z",
                     "2026-10-16T11:05:00Z")
        store = reseal(path, manifest)
    root = _copy_policy(tmp_path)
    graph.close_checkpoint_graph()
    graph._fiction_store_cached.cache_clear()
    calls = []

    class RouterModel:
        def with_structured_output(self, schema):
            return self

        def invoke(self, messages):
            calls.append(messages[-1][1])
            return SimpleNamespace(intent=graph.classify(messages[-1][1]))

    monkeypatch.setenv("RETAILIQ_MODE", "full")
    monkeypatch.setenv("RETAILIQ_FICTION_DB", str(path))
    monkeypatch.setenv("RETAILIQ_FICTION_MANIFEST", str(manifest))
    monkeypatch.setenv("RETAILIQ_FICTION_KNOWLEDGE_ROOT", str(root))
    monkeypatch.setenv("RETAILIQ_CHAT_DB", str(tmp_path / "sessions.sqlite3"))
    monkeypatch.setenv("RETAILIQ_CHECKPOINT_DB", str(tmp_path / "checkpoints.sqlite3"))
    monkeypatch.setenv("LANGSMITH_TRACING", "false")
    monkeypatch.setattr(graph, "chat_model", lambda: RouterModel())
    return graph, calls, store


def test_uc01_t03_followup_uses_committed_case_even_without_snapshots(monkeypatch, fiction, tmp_path):
    """A+B end-to-end; missing snapshots must not erase the case reference."""
    from fastapi.testclient import TestClient
    from retailiq.api import app
    from retailiq.infrastructure.sessions import last_committed_case_binding

    graph, model_calls, store = _uc01_context_client(monkeypatch, tmp_path, fiction)
    from retailiq.domain import backorder as backorder_domain
    actual = backorder_domain.investigate_backorder
    tool_case_ids = []

    def tracked_tool(store, case_id, *, knowledge_root):
        tool_case_ids.append(case_id)
        return actual(store, case_id, knowledge_root=knowledge_root)

    monkeypatch.setattr(backorder_domain, "investigate_backorder", tracked_tool)
    try:
        with TestClient(app) as client:
            signed_in_client(app, client=client)
            sid = client.post("/api/sessions", json={}).json()["id"]
            first = client.post("/ask", json={
                "session_id": sid, "question": f"Investigate backorder {C1}"})
            assert first.status_code == 200, first.text
            assert first.json()["disposition"] == "INSUFFICIENT_EVIDENCE"
            assert first.json()["records"] == []
            committed = last_committed_case_binding(sid)
            assert committed["case_id"] == C1
            assert committed["cutoff"] == "2026-10-16T12:00:00Z"
            assert committed["source_sha256"] == store.release["runtime_sha256"]
            assert committed["case_ref"] == f"fulfillment_cases/{C1}"

            second = client.post("/ask", json={
                "session_id": sid, "question": "Chính sách nào áp dụng?"})
            assert second.status_code == 200, second.text
            result = second.json()
            assert result["intent"] == "backorder"
            assert result["disposition"] == "INSUFFICIENT_EVIDENCE"
            assert result["as_of"] == committed["cutoff"]
            assert result["capability_plan"]["source"] == "committed_session_case"
            assert result["capability_plan"]["case_id"] == C1
            assert "FR-WH-2026-10-04" in result["answer"]
            assert any("knowledge_documents/" in ref
                       for item in result["findings"] for ref in item["evidence_refs"])
            assert len(model_calls) == 2  # One explicit-case router + one policy quote model; no re-route.
            assert tool_case_ids == [C1, C1]  # Real reviewed domain invocation twice.
            assert len(client.get(f"/api/sessions/{sid}").json()["messages"]) == 4
    finally:
        graph.close_checkpoint_graph()
        graph._fiction_store_cached.cache_clear()




def test_uc01_t05_policy_clauses_via_graph_and_http(monkeypatch, fiction, tmp_path):
    """Real compiled graph + verified fixture, fake router and quote model."""
    from fastapi.testclient import TestClient
    from types import SimpleNamespace
    from retailiq.api import app
    from retailiq.orchestration import week1_graph as graph

    graph, _, store = _uc01_context_client(monkeypatch, tmp_path, fiction,
                                            with_candidate=True)
    from retailiq.rag.policy_explanation import PolicyQuote

    calls = {"route": 0, "quote": 0}
    approval = ("An authorized Operations Manager must approve the request before any "
                "transfer, reservation or order change is executed.")
    freshness = "Observations more than 24 hours old are not sufficient to authorize a transfer."

    class SafeModel:
        def with_structured_output(self, schema):
            self.kind = schema.__name__
            return self

        def invoke(self, messages):
            if self.kind == "Route":
                calls["route"] += 1
                return SimpleNamespace(intent=graph.classify(messages[-1][1]))
            assert self.kind == PolicyQuote.__name__
            payload = json.loads(messages[-1][1])
            calls["quote"] += 1
            if "24" in payload["question"]:
                return PolicyQuote(section="inventory-information", quote=freshness)
            return PolicyQuote(section="review-and-approval", quote=approval)

    monkeypatch.setattr(graph, "chat_model", lambda: SafeModel())
    try:
        with TestClient(app) as client:
            signed_in_client(app, client=client)
            sid = client.post("/api/sessions", json={}).json()["id"]
            first = client.post("/ask", json={
                "session_id": sid, "question": f"Investigate backorder {C1}"})
            assert first.status_code == 200, first.text
            assert calls == {"route": 1, "quote": 0}
            assert first.json()["contexts"] == []

            approval_response = client.post("/ask", json={
                "session_id": sid, "question": "Vì sao cần Manager phê duyệt?"})
            assert approval_response.status_code == 200, approval_response.text
            result = approval_response.json()
            assert calls == {"route": 1, "quote": 1}
            assert result["disposition"] == first.json()["disposition"]
            assert result["approval_status"] == "NOT_REQUESTED"
            assert result["source"]["sha256"] == store.release["runtime_sha256"]
            assert result["as_of"] == first.json()["as_of"]
            assert result["contexts"][0]["metadata"]["section"] == "review-and-approval"
            assert approval in result["answer"]
            assert "[S1]" in result["answer"]
            assert any("#review-and-approval" in ref for ref in result["evidence_refs"])

            freshness_response = client.post("/ask", json={
                "session_id": sid,
                "question": "Chính sách yêu cầu gì khi snapshot quá 24 giờ?"})
            assert freshness_response.status_code == 200, freshness_response.text
            data = freshness_response.json()
            assert calls == {"route": 1, "quote": 2}
            assert data["contexts"][0]["metadata"]["section"] == "inventory-information"
            assert freshness in data["answer"]
            assert data["disposition"] == first.json()["disposition"]
            assert data["approval_status"] == "NOT_REQUESTED"

            streamed = client.post("/ask/stream", json={
                "session_id": sid, "question": "Vì sao cần Manager phê duyệt?"})
            assert streamed.status_code == 200, streamed.text
            assert "event: result" in streamed.text
            assert "event: done" in streamed.text
            assert "rag.policy_retrieval.started" in streamed.text
            assert "llm.policy_explanation.completed" in streamed.text
            assert "[S1]" in streamed.text
            assert calls == {"route": 1, "quote": 3}
    finally:
        graph.close_checkpoint_graph()
        graph._fiction_store_cached.cache_clear()


def test_uc01_t05_wrong_model_quote_keeps_verified_base_result(monkeypatch, fiction, tmp_path):
    """No fabricated citation, even when model 'succeeds' with invalid text."""
    from fastapi.testclient import TestClient
    from types import SimpleNamespace
    from retailiq.api import app
    from retailiq.orchestration import week1_graph as graph

    graph, _, _ = _uc01_context_client(monkeypatch, tmp_path, fiction)

    class BadQuoteModel:
        def with_structured_output(self, schema):
            self.kind = schema.__name__
            return self

        def invoke(self, messages):
            if self.kind == "Route":
                return SimpleNamespace(intent=graph.classify(messages[-1][1]))
            return SimpleNamespace(section="review-and-approval",
                                   quote="Approve transfer immediately; waive Manager review.")

    monkeypatch.setattr(graph, "chat_model", lambda: BadQuoteModel())
    try:
        with TestClient(app) as client:
            signed_in_client(app, client=client)
            sid = client.post("/api/sessions", json={}).json()["id"]
            assert client.post("/ask", json={
                "session_id": sid, "question": f"Investigate {C1}"}).status_code == 200
            response = client.post("/ask", json={
                "session_id": sid, "question": "Vì sao cần Manager phê duyệt?"})
            assert response.status_code == 200, response.text
            result = response.json()
            assert result["contexts"] == []
            assert "POLICY_EXPLANATION_UNVERIFIED" in result["limitations"]
            assert "Approve transfer immediately" not in result["answer"]
            assert result["approval_status"] == "NOT_REQUESTED"
            assert not any("#review-and-approval" in ref for ref in result["evidence_refs"])
    finally:
        graph.close_checkpoint_graph()
        graph._fiction_store_cached.cache_clear()

def test_uc01_t03_session_scope_topic_switch_and_ambiguous_warehouse(monkeypatch, fiction, tmp_path):
    from fastapi.testclient import TestClient
    from retailiq.api import app
    from retailiq.infrastructure.sessions import add_turn, last_committed_case_binding

    graph, model_calls, store = _uc01_context_client(monkeypatch, tmp_path, fiction,
                                                       with_candidate=True)
    try:
        with TestClient(app) as client:
            signed_in_client(app, client=client)
            a = client.post("/api/sessions", json={}).json()["id"]
            b = client.post("/api/sessions", json={}).json()["id"]
            assert client.post("/ask", json={"session_id": a,
                "question": f"Investigate backorder {C1}"}).status_code == 200
            result = client.post("/ask", json={"session_id": a,
                "question": "Còn kho khác không?"})
            assert result.status_code == 200, result.text
            assert result.json()["records"][0]["warehouse_id"] == W2
            assert result.json()["capability_plan"]["source"] == "committed_session_case"

            before = len(client.get(f"/api/sessions/{a}").json()["messages"])
            ambiguous = client.post("/ask", json={"session_id": a,
                "question": "Kho thứ hai thì sao?"})
            assert ambiguous.status_code == 422
            assert "warehouse ID" in ambiguous.json()["detail"]
            assert len(client.get(f"/api/sessions/{a}").json()["messages"]) == before

            cross = client.post("/ask", json={"session_id": b,
                "question": "Chính sách nào áp dụng?"})
            assert cross.status_code == 422
            assert client.get(f"/api/sessions/{b}").json()["messages"] == []

            # A successful independent topic breaks implicit case inheritance.
            add_turn(a, "What are top products?", {
                "intent": "top", "active_agent": "sales_agent", "answer": "Sample ranking",
                "records": [], "contexts": []})
            assert last_committed_case_binding(a) is None
            unrelated = client.post("/ask", json={"session_id": a,
                "question": "Chính sách nào áp dụng?"})
            assert unrelated.status_code == 422
            assert len(model_calls) == 1
    finally:
        graph.close_checkpoint_graph()
        graph._fiction_store_cached.cache_clear()


def test_uc01_t03_tampered_evidence_and_explicit_case_override(monkeypatch, fiction, tmp_path):
    """The pinned release validates inherited authority, not user/assistant prose."""
    from fastapi.testclient import TestClient
    from retailiq.api import app
    from retailiq.infrastructure.sessions import last_committed_case_binding

    graph, _, store = _uc01_context_client(monkeypatch, tmp_path, fiction)
    try:
        with TestClient(app) as client:
            signed_in_client(app, client=client)
            sid = client.post("/api/sessions", json={}).json()["id"]
            assert client.post("/ask", json={"session_id": sid,
                "question": f"Investigate {C1}"}).status_code == 200
            db = tmp_path / "sessions.sqlite3"
            with sqlite3.connect(db) as c:
                raw = c.execute("SELECT evidence_json FROM messages WHERE session_id=? AND role='assistant' ORDER BY id DESC LIMIT 1",
                                (sid,)).fetchone()[0]
                payload = json.loads(raw)
                payload["case_binding"]["source_sha256"] = "0"*64
                c.execute("UPDATE messages SET evidence_json=? WHERE session_id=? AND role='assistant'",
                          (json.dumps(payload), sid))
            # Well-formed but mismatching source hash cannot authorize a follow-up.
            stale = client.post("/ask", json={"session_id": sid,
                "question": "Chính sách nào áp dụng?"})
            assert stale.status_code == 422
            assert "source/cutoff changed" in stale.json()["detail"]
            assert last_committed_case_binding(sid)["source_sha256"] == "0"*64

            # Explicit CASE-ID takes precedence over inherited, untrusted source hash.
            fresh = client.post("/ask", json={"session_id": sid,
                "question": f"Investigate {C1}"})
            assert fresh.status_code == 200, fresh.text
            assert fresh.json()["capability_plan"]["source"] == "validated_explicit_case_id"
            assert last_committed_case_binding(sid)["source_sha256"] == store.release["runtime_sha256"]

            with sqlite3.connect(db) as c:
                c.execute("UPDATE messages SET evidence_json='corrupted' WHERE session_id=? AND role='assistant' AND id=(SELECT MAX(id) FROM messages WHERE session_id=? AND role='assistant')",
                          (sid, sid))
            missing = client.post("/ask", json={"session_id": sid,
                "question": "Chính sách nào áp dụng?"})
            assert missing.status_code == 422
            assert "explicit CASE-ID" in missing.json()["detail"]
    finally:
        graph.close_checkpoint_graph()
        graph._fiction_store_cached.cache_clear()


def test_uc01_t03_failed_turn_checkpoint_is_not_committed_context(monkeypatch, fiction, tmp_path):
    from fastapi.testclient import TestClient
    from retailiq.api import app
    from retailiq.api import http
    from retailiq.infrastructure.sessions import last_committed_case_binding

    graph, _, _ = _uc01_context_client(monkeypatch, tmp_path, fiction)
    genuine_commit = http.add_turn

    def failed_commit(*args, **kwargs):
        raise RuntimeError("controlled commit failure")

    try:
        with TestClient(app) as client:
            signed_in_client(app, client=client)
            sid = client.post("/api/sessions", json={}).json()["id"]
            monkeypatch.setattr(http, "add_turn", failed_commit)
            failed = client.post("/ask", json={"session_id": sid,
                "question": f"Investigate {C1}"})
            assert failed.status_code == 503
            monkeypatch.setattr(http, "add_turn", genuine_commit)
            assert last_committed_case_binding(sid) is None
            assert client.get(f"/api/sessions/{sid}").json()["messages"] == []
            followup = client.post("/ask", json={"session_id": sid,
                "question": "Chính sách nào áp dụng?"})
            assert followup.status_code == 422
            assert client.get(f"/api/sessions/{sid}").json()["messages"] == []
    finally:
        graph.close_checkpoint_graph()
        graph._fiction_store_cached.cache_clear()



def test_uc01_t03_explicit_other_case_replaces_committed_context(monkeypatch, fiction, tmp_path):
    """A different explicit CASE-ID is authoritative; next follow-up inherits it."""
    from fastapi.testclient import TestClient
    from retailiq.api import app
    from retailiq.infrastructure.sessions import last_committed_case_binding

    second_case = "CASE-99999999-9999-4999-8999-999999999999"
    path, manifest, _ = fiction
    with sqlite3.connect(path) as conn:
        conn.execute("""INSERT INTO fulfillment_cases
            SELECT ?, order_id, order_item_id, product_id, request_qty,
                   assigned_warehouse_id, case_date
            FROM fulfillment_cases WHERE case_id=?""", (second_case, C1))
        conn.execute("INSERT INTO operational_events VALUES (?,?,?,?,?)",
                     ("event-for-second", second_case, "evidence_cutoff_reached",
                      "2026-10-17T12:00:00Z", "2026-10-17T12:01:00Z"))
        conn.execute("""INSERT INTO warehouse_eligibility
            SELECT ?, warehouse_id, eligible, reason_code FROM warehouse_eligibility
            WHERE case_id=?""", (second_case, C1))
    store = reseal(path, manifest)
    graph, _, _ = _uc01_context_client(monkeypatch, tmp_path, fiction)
    try:
        with TestClient(app) as client:
            signed_in_client(app, client=client)
            sid = client.post("/api/sessions", json={}).json()["id"]
            assert client.post("/ask", json={"session_id": sid,
                "question": f"Investigate backorder {C1}"}).status_code == 200
            explicit = client.post("/ask", json={"session_id": sid,
                "question": f"Investigate backorder {second_case}"})
            assert explicit.status_code == 200, explicit.text
            assert explicit.json()["capability_plan"]["case_id"] == second_case
            assert explicit.json()["capability_plan"]["source"] == "validated_explicit_case_id"
            assert last_committed_case_binding(sid)["case_id"] == second_case

            followup = client.post("/ask", json={"session_id": sid,
                "question": "Which warehouse policy applies?"})
            assert followup.status_code == 200, followup.text
            assert followup.json()["capability_plan"]["case_id"] == second_case
            assert followup.json()["as_of"] == "2026-10-17T12:00:00Z"
    finally:
        graph.close_checkpoint_graph()
        graph._fiction_store_cached.cache_clear()


def test_t04_order_and_inventory_shared_domain_contract(fiction):
    path, manifest, store = fiction
    order = store.order(O1)
    assert order["scope"]["order_id"] == O1
    assert order["data"]["lines"][0]["order_item_id"] == I1
    assert order["record_refs"] == [f"orders/{O1}", f"order_items/{I1}"]
    assert "CUSTOMER_SECRET" not in str(order)
    assert "release-recorded" in " ".join(order["limitations"])

    assert store.inventory(P1, W1)["data"][0]["available_snapshot"] == 3
    unknown_warehouse = "00000000-0000-4000-8000-000000000000"
    result = store.inventory(P1, unknown_warehouse)
    assert result["data"] == []
    assert result["limitations"] == ["WAREHOUSE_NOT_FOUND"]
    assert result["scope"]["warehouse_id"] == unknown_warehouse


@pytest.mark.parametrize("field,value,reason", [
    ("quantity", 0, "quantity"),
    ("discount_pct", 101, "discount"),
    ("unit_price", -1, "financial amount"),
    ("product_id", "99999999-9999-4999-8999-999999999999", "unknown product"),
])
def test_t04_order_rejects_corrupt_line_source(fiction, field, value, reason):
    path, manifest, store = fiction
    with sqlite3.connect(path) as conn:
        conn.execute(f"UPDATE order_items SET {field}=? WHERE order_item_id=?", (value, I1))
    with pytest.raises(FictionDataError, match="changed since release"):
        store.order(O1)
    store = reseal(path, manifest)
    with pytest.raises(FictionDataError, match=reason):
        store.order(O1)


def test_t04_order_rejects_invalid_shipment_identity(fiction):
    path, manifest, _ = fiction
    with sqlite3.connect(path) as conn:
        conn.execute("INSERT INTO shipments VALUES (?,?,?,?,?,?)",
                     ("not-a-uuid", O1, W1, "2026-10-17", "2026-10-18", "delivered"))
    store = reseal(path, manifest)
    with pytest.raises(ValueError, match="canonical Fiction UUID"):
        store.order(O1)


def test_t04_adapter_rejects_error_before_decoding_and_wrong_source(fiction):
    from retailiq.mcp_adapter import decode_tool_result, _verify_envelope
    from types import SimpleNamespace

    malicious = SimpleNamespace(status="error", artifact={
        "data": [], "source": {"id": "fiction-retail/sqlite"},
        "scope": {}, "record_refs": [], "limitations": [],
    })
    with pytest.raises(ValueError, match="execution error"):
        decode_tool_result(malicious)

    _, _, store = fiction
    result = store.inventory(P1)
    with pytest.raises(ValueError, match="source or evidence invalid"):
        _verify_envelope(result, "0" * 64, "inventory_lookup", {"product": P1, "warehouse_id": None})
    assert _verify_envelope(result, store.release["runtime_sha256"],
                            "inventory_lookup", {"product": P1, "warehouse_id": None}) == result


@pytest.mark.parametrize("question,has_warehouse", [
    ("Tồn kho của {sku} là bao nhiêu?", False),
    ("Tồn kho {sku} tại kho {warehouse}", True),
    ("Show stock for {sku} across all warehouses", False),
    ("Stock of {sku} at warehouse {warehouse}", True),
    ("tồn kho của {sku} ở các kho?", False),
])
def test_t04_bounded_stock_route_vietnamese_and_english(question, has_warehouse):
    from retailiq.orchestration.week1_graph import _fiction_inventory_request
    sku = "FR-" + sha256(P1.encode()).hexdigest()[:16].upper()
    parsed = _fiction_inventory_request(question.format(sku=sku, warehouse=W1))
    assert parsed == (sku, W1 if has_warehouse else None)


@pytest.mark.parametrize("question", [
    "Tồn kho {sku} ngày 20/10/2026?",
    "Tồn kho {sku} tháng 10?",
    "Tồn kho {sku} trong tuần trước?",
    "Stock for {sku} as of 2026-10-20",
    "Stock for {sku} in October 2026",
    "Stock for {sku} today?",
    "Show current stock for {sku}",
    "Show stock for {sku} in 10/2026",
])
def test_t04_stock_time_scope_never_silently_dropped(question):
    from retailiq.orchestration.week1_graph import _fiction_inventory_request, InvalidFictionScope
    sku = "FR-" + sha256(P1.encode()).hexdigest()[:16].upper()
    with pytest.raises(InvalidFictionScope, match="UNSUPPORTED_TEMPORAL_SCOPE"):
        _fiction_inventory_request(question.format(sku=sku))


@pytest.mark.parametrize("question", [
    "Tồn kho và doanh thu của {sku}?",
    "Stock and revenue for {sku}",
    "So sánh tồn kho {sku} và đơn hàng",
    "Stock for {sku} and order status",
])
def test_t04_stock_mixed_intent_is_not_dropped(question):
    from retailiq.orchestration.week1_graph import _fiction_inventory_request, InvalidFictionScope
    sku = "FR-" + sha256(P1.encode()).hexdigest()[:16].upper()
    with pytest.raises(InvalidFictionScope, match="MULTI_INTENT_UNSUPPORTED"):
        _fiction_inventory_request(question.format(sku=sku))


def test_t04_stock_unbound_warehouse_id_is_rejected():
    from retailiq.orchestration.week1_graph import _fiction_inventory_request, InvalidFictionScope
    sku = "FR-" + sha256(P1.encode()).hexdigest()[:16].upper()
    with pytest.raises(InvalidFictionScope, match="warehouse UUID"):
        _fiction_inventory_request(f"Stock {sku} at {W1}")


def test_t04_corrupt_shipment_warehouse_rejected_from_shared_domain(fiction):
    path, manifest, _ = fiction
    shipment_id = "88888888-8888-4888-8888-888888888888"
    unknown = "99999999-9999-4999-8999-999999999999"
    with sqlite3.connect(path) as conn:
        conn.execute("INSERT INTO shipments VALUES (?,?,?,?,?,?)",
                     (shipment_id, O1, unknown, "2026-10-17", None, "shipped"))
    store = reseal(path, manifest)
    with pytest.raises(FictionDataError, match="unknown warehouse"):
        store.order(O1)


def test_t04_mcp_strict_field_allowlist_blocks_unexpected_pii(fiction):
    import copy
    from retailiq.mcp_adapter import _verify_envelope
    _, _, store = fiction
    evidence = store.order(O1)
    expected = store.release["runtime_sha256"]
    assert _verify_envelope(evidence, expected, "order_lookup",
                            {"order_id": O1}) == evidence

    injected = copy.deepcopy(evidence)
    injected["data"]["order"]["customer_phone"] = "+1-555-0100"
    with pytest.raises(ValueError, match="invalid identity/size"):
        _verify_envelope(injected, expected, "order_lookup", {"order_id": O1})

    injected = copy.deepcopy(evidence)
    injected["scope"]["customer_email"] = "secret@example.invalid"
    with pytest.raises(ValueError, match="scope contains unexpected fields"):
        _verify_envelope(injected, expected, "order_lookup", {"order_id": O1})

    injected = copy.deepcopy(evidence)
    injected["source"]["credentials"] = "unexpected"
    with pytest.raises(ValueError, match="source or evidence invalid"):
        _verify_envelope(injected, expected, "order_lookup", {"order_id": O1})

    injected = copy.deepcopy(evidence)
    injected["data"]["lines"][0]["unit_price"] = -1
    with pytest.raises(ValueError, match="financial amount"):
        _verify_envelope(injected, expected, "order_lookup", {"order_id": O1})
