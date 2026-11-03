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
                              "fulfillment_policies", "knowledge_documents"}:
                c.execute(f'CREATE TABLE "{table}" (dummy TEXT)')
        sku = lambda pid: "FR-" + sha256(pid.encode()).hexdigest()[:16].upper()
        c.executemany('INSERT INTO products VALUES(?,?,?,?,?,?)',
                      [(P1, sku(P1), "Device", "electronics", "Brand", 20.0),
                       (P2, sku(P2), "Other", "electronics", "Brand", 25.0)])
        c.execute("INSERT INTO orders VALUES (?,?,?,?,?)", (O1, "CUSTOMER_SECRET", "2026-10-15", "delivered", 20.0))
        c.execute("INSERT INTO order_items VALUES (?,?,?,?,?,?)", (I1, O1, P1, 2, 10.0, 0))
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
