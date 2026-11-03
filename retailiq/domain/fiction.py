"""Reviewed, read-only business queries for the unified Fiction Retail snapshot.

Use ``FictionStore.open`` after verifying the manifest, never the legacy demo DB.
These functions return scoped *facts*, not business approvals or live telemetry.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from contextlib import closing
from decimal import Decimal, ROUND_HALF_UP
from hashlib import sha256
import json
from pathlib import Path
import re
import sqlite3
from uuid import UUID

from retailiq.infrastructure.sqlite import query

RELEASE = "fiction-retail-unified-v1.0.0"
_UUID = re.compile(r"^[a-fA-F0-9]{8}-(?:[a-fA-F0-9]{4}-){3}[a-fA-F0-9]{12}$")
_SKU = re.compile(r"^FR-[0-9A-F]{16}$")
_LIMIT = 100


class FictionDataError(ValueError):
    """Missing, inconsistent, or incompatible Fiction data; no legacy fallback."""


def _id(value: str) -> str:
    if not isinstance(value, str) or not _UUID.fullmatch(value):
        raise ValueError("Expected canonical Fiction UUID")
    return str(UUID(value))


def _period(month: str) -> tuple[str, str]:
    if not isinstance(month, str) or not re.fullmatch(r"20\d\d-(?:0[1-9]|1[0-2])", month):
        raise ValueError("Expected YYYY-MM calendar month")
    first = date.fromisoformat(month + "-01")
    following = date(first.year + (first.month == 12), first.month % 12 + 1, 1)
    return first.isoformat(), following.isoformat()


def _money(value: object) -> Decimal:
    result = Decimal(str(value))
    if not result.is_finite() or result < 0:
        raise FictionDataError("Invalid financial amount")
    return result


def _usd(value: Decimal) -> str:
    return str(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def verify_release(db_path: str | Path, manifest_path: str | Path) -> dict:
    """Fail closed if bytes, schema, manifest and immutable identity diverge."""
    db_path, manifest_path = Path(db_path).resolve(), Path(manifest_path).resolve()
    if not db_path.is_file() or not manifest_path.is_file():
        raise FictionDataError("Fiction SQLite and release manifest are both required")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("pack_version") != RELEASE or not re.fullmatch(
        r"[0-9a-f]{64}", str(manifest.get("runtime_sha256", ""))
    ):
        raise FictionDataError("Unsupported or incomplete Fiction release manifest")
    actual_sha = sha256()
    with db_path.open("rb") as f:
        for part in iter(lambda: f.read(1024 * 1024), b""):
            actual_sha.update(part)
    if actual_sha.hexdigest() != manifest["runtime_sha256"]:
        raise FictionDataError("Fiction binary SHA-256 does not match manifest")
    with closing(sqlite3.connect(db_path.as_uri() + "?mode=ro", uri=True)) as conn:
        conn.execute("PRAGMA query_only=ON")
        if conn.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise FictionDataError("Fiction integrity_check failed")
        if conn.execute("PRAGMA foreign_key_check").fetchone() is not None:
            raise FictionDataError("Fiction foreign_key_check failed")
        counts = manifest.get("table_counts")
        if not isinstance(counts, dict) or len(counts) != 27:
            raise FictionDataError("Expected 27-table unified schema")
        for table, expected in counts.items():
            if not re.fullmatch(r"[a-z_0-9]+", table) or not isinstance(expected, int):
                raise FictionDataError("Invalid table in manifest")
            if conn.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0] != expected:
                raise FictionDataError(f"Fiction row-count mismatch: {table}")
        metadata = dict(conn.execute("SELECT key, value FROM metadata"))
        if (metadata.get("version") != RELEASE or
            metadata.get("dataset_business_as_of") != manifest.get("dataset_business_as_of") or
            metadata.get("output_checksum") != manifest.get("content_sha256")):
            raise FictionDataError("Fiction embedded release metadata mismatch")
        for product_id, sku in conn.execute("SELECT product_id, sku FROM products"):
            try:
                canonical_id = _id(product_id)
            except ValueError as exc:
                raise FictionDataError("Invalid product_id") from exc
            expected_sku = "FR-" + sha256(canonical_id.encode()).hexdigest()[:16].upper()
            if sku != expected_sku:
                raise FictionDataError("Fiction product_id / SKU mapping mismatch")
    return {
        "pack_version": RELEASE,
        "runtime_sha256": manifest["runtime_sha256"],
        "dataset_business_as_of": manifest["dataset_business_as_of"],
        "business_timezone": manifest["business_timezone"],
        "table_count": len(counts),
        "product_count": counts["products"],
    }


class FictionStore:
    """SQL facts on one manifest-verified snapshot; no arbitrary user SQL."""

    def __init__(self, db_path: str | Path, release: dict):
        self.db_path = Path(db_path).resolve()
        self.release = release

    @classmethod
    def open(cls, db_path: str | Path, manifest_path: str | Path) -> "FictionStore":
        return cls(db_path, verify_release(db_path, manifest_path))

    def _q(self, sql: str, args: tuple = ()) -> list[dict]:
        return query(sql, args, db_path=self.db_path)

    def _result(self, data: object, *, scope: dict, refs: list[str],
                temporal: dict | None = None, limitations: list[str] | None = None) -> dict:
        notices = list(limitations or [])
        if len(refs) > _LIMIT:
            notices.append("RECORD_REFS_TRUNCATED: only the first 100 source references are shown")
        return {
            "data": data,
            "source": {"id": "fiction-retail/sqlite", "version": self.release["pack_version"],
                       "sha256": self.release["runtime_sha256"]},
            "scope": scope, "record_refs": refs[:_LIMIT],
            "temporal": temporal or {"dataset_business_as_of": self.release["dataset_business_as_of"]},
            "limitations": notices,
        }

    def resolve_product(self, value: str) -> str | None:
        if isinstance(value, str) and _SKU.fullmatch(value):
            rows = self._q("SELECT product_id FROM products WHERE sku=?", (value,))
            return rows[0]["product_id"] if rows else None
        product_id = _id(value)
        rows = self._q("SELECT product_id FROM products WHERE product_id=?", (product_id,))
        return rows[0]["product_id"] if rows else None

    def product(self, value: str) -> dict:
        pid = self.resolve_product(value)
        rows = self._q("SELECT product_id, sku, name, category, brand, price "
                       "FROM products WHERE product_id=?", (pid,)) if pid else []
        return self._result(rows[0] if rows else None, scope={"product_id": pid},
                            refs=[f"products/{pid}"] if pid else [],
                            limitations=["Imported list price has no effective date or verified currency-specific offer"] if rows else ["PRODUCT_NOT_FOUND"])

    def order(self, order_id: str) -> dict:
        oid = _id(order_id)
        orders = self._q("SELECT order_id, order_date, order_status, total_amount "
                         "FROM orders WHERE order_id=?", (oid,))
        if not orders:
            return self._result(None, scope={"order_id": oid}, refs=[], limitations=["ORDER_NOT_FOUND"])
        lines = self._q("SELECT order_item_id, product_id, quantity, unit_price, discount_pct "
                        "FROM order_items WHERE order_id=? ORDER BY order_item_id", (oid,))
        shipments = self._q("SELECT shipment_id, warehouse_id, shipped_date, delivered_date, shipment_state "
                            "FROM shipments WHERE order_id=? ORDER BY shipment_id", (oid,))
        return self._result({"order": orders[0], "lines": lines, "shipments": shipments},
                            scope={"order_id": oid}, refs=[f"orders/{oid}"] +
                            [f"order_items/{r['order_item_id']}" for r in lines] +
                            [f"shipments/{r['shipment_id']}" for r in shipments],
                            temporal={"order_date": orders[0]["order_date"]},
                            limitations=["Order status does not prove payment settlement or live delivery status"])

    def inventory(self, product: str, warehouse_id: str | None = None) -> dict:
        pid = self.resolve_product(product)
        wid = _id(warehouse_id) if warehouse_id is not None else None
        rows = self._q("SELECT inventory_id, product_id, warehouse_id, quantity_on_hand, "
                       "reserved_quantity, last_restocked_date FROM inventory "
                       "WHERE product_id=? AND (? IS NULL OR warehouse_id=?) ORDER BY warehouse_id",
                       (pid, wid, wid)) if pid else []
        for row in rows:
            on_hand, reserved = row["quantity_on_hand"], row["reserved_quantity"]
            if type(on_hand) is not int or type(reserved) is not int or not 0 <= reserved <= on_hand:
                raise FictionDataError("Invalid stock evidence")
            row["available_snapshot"] = on_hand - reserved
        return self._result(rows, scope={"product_id": pid, "warehouse_id": wid},
                            refs=[f"inventory/{r['inventory_id']}" for r in rows],
                            limitations=["UNDATED_INVENTORY: snapshot time unknown; not current or historical-at-query-period stock"]
                            + (["NO_INVENTORY_RECORDS: not equivalent to zero stock"] if not rows else []))

    def top_sellers(self, month: str, limit: int = 5) -> dict:
        first, end = _period(month)
        if type(limit) is not int or not 1 <= limit <= 20:
            raise ValueError("Top-seller limit must be 1..20")
        rows = self._q("SELECT oi.product_id, p.sku, SUM(oi.quantity) AS delivered_units "
                       "FROM orders o JOIN order_items oi ON oi.order_id=o.order_id "
                       "JOIN products p ON p.product_id=oi.product_id "
                       "WHERE o.order_status='delivered' AND o.order_date>=? AND o.order_date<? "
                       "GROUP BY oi.product_id, p.sku ORDER BY delivered_units DESC, oi.product_id ASC LIMIT ?",
                       (first, end, limit))
        as_of = self.release["dataset_business_as_of"][:10]
        coverage = self._q("SELECT MIN(order_date) AS earliest, MAX(order_date) AS latest FROM orders")[0]
        earliest = coverage["earliest"]
        latest = coverage["latest"]
        # A month spanning the first/last observed date is not necessarily complete.
        incomplete = (not earliest or not latest or first < earliest or
                      date.fromisoformat(end) > date.fromisoformat(latest) + timedelta(days=1) or
                      end > as_of)
        return self._result(rows, scope={"period_start": first, "period_end": end, "status": "delivered"},
                            refs=[f"products/{r['product_id']}" for r in rows],
                            temporal={"period_start": first, "period_end_exclusive": end,
                                      "dataset_business_as_of": self.release["dataset_business_as_of"]},
                            limitations=(["PARTIAL_OR_FUTURE_PERIOD: cannot assert complete calendar-month ranking"] if incomplete else [])
                            + ["Delivered units are not settled sales or net revenue"])

    def refund(self, return_id: str) -> dict:
        rid = _id(return_id)
        rows = self._q("SELECT r.return_id, r.order_id, r.product_id, r.return_date, "
                       "r.refund_amount, r.return_reason_code, o.total_amount "
                       "FROM returns r JOIN orders o ON o.order_id=r.order_id "
                       "WHERE r.return_id=?", (rid,))
        if not rows:
            return self._result(None, scope={"return_id": rid}, refs=[], limitations=["RETURN_NOT_FOUND"])
        entry = rows[0]
        lines = self._q("SELECT order_item_id, quantity, unit_price, discount_pct FROM order_items "
                        "WHERE order_id=? AND product_id=?", (entry["order_id"], entry["product_id"]))
        item_net = sum((_money(r["quantity"]) * _money(r["unit_price"]) *
                        (Decimal(100) - _money(r["discount_pct"])) / Decimal(100)
                        for r in lines), Decimal(0))
        refund_value = _money(entry["refund_amount"])
        order_value = _money(entry["total_amount"])
        entry["returned_product_lines_net_usd"] = _usd(item_net)
        entry["refund_above_order_value"] = refund_value > order_value
        entry["refund_above_returned_product_lines"] = refund_value > item_net
        return self._result(entry, scope={"return_id": rid, "order_id": entry["order_id"],
                                          "product_id": entry["product_id"]},
                            refs=[f"returns/{rid}", f"orders/{entry['order_id']}"] +
                            [f"order_items/{r['order_item_id']}" for r in lines],
                            temporal={"return_date": entry["return_date"]},
                            limitations=["Recorded refund amount is not evidence of approved or completed payment"] +
                            (["NO_MATCHING_ORDER_LINE"] if not lines else []))

    def fulfillment_case(self, case_id: str) -> dict:
        if not isinstance(case_id, str) or not re.fullmatch(r"CASE-[0-9a-f-]{36}", case_id):
            raise ValueError("Invalid Fiction case ID")
        cases = self._q("SELECT case_id, order_id, order_item_id, product_id, request_qty, "
                        "assigned_warehouse_id, case_date FROM fulfillment_cases WHERE case_id=?", (case_id,))
        if not cases:
            return self._result(None, scope={"case_id": case_id}, refs=[], limitations=["CASE_NOT_FOUND"])
        c = cases[0]
        events = self._q("SELECT event_id, event_type, occurred_at, recorded_at FROM operational_events "
                         "WHERE case_id=? ORDER BY occurred_at", (case_id,))
        cutoffs = [r["occurred_at"] for r in events if r["event_type"] == "evidence_cutoff_reached"]
        if len(cutoffs) != 1:
            raise FictionDataError("Case must have exactly one evidence cutoff")
        cutoff = datetime.fromisoformat(cutoffs[0].replace("Z", "+00:00"))
        snapshots = self._q("SELECT snapshot_id, product_id, warehouse_id, observed_at, received_at, "
                            "on_hand, reserved FROM inventory_snapshots_v2 WHERE case_id=? "
                            "ORDER BY observed_at, snapshot_id", (case_id,))
        eligibility = self._q("SELECT warehouse_id, eligible, reason_code FROM warehouse_eligibility "
                              "WHERE case_id=? ORDER BY warehouse_id", (case_id,))
        routes = {r["warehouse_id"]: r for r in eligibility}
        candidates = []
        for snap in snapshots:
            observed = datetime.fromisoformat(snap["observed_at"].replace("Z", "+00:00"))
            received = datetime.fromisoformat(snap["received_at"].replace("Z", "+00:00"))
            allowed = routes.get(snap["warehouse_id"], {}).get("eligible") == 1
            usable = (snap["product_id"] == c["product_id"] and
                      observed <= cutoff and received <= cutoff and
                      timedelta(0) <= cutoff - observed <= timedelta(hours=24) and
                      type(snap["on_hand"]) is int and type(snap["reserved"]) is int and
                      snap["on_hand"] >= snap["reserved"] >= 0 and allowed and
                      snap["on_hand"] - snap["reserved"] >= c["request_qty"])
            if usable:
                candidates.append({"snapshot_id": snap["snapshot_id"],
                                   "warehouse_id": snap["warehouse_id"],
                                   "available_at_observation": snap["on_hand"] - snap["reserved"]})
        # One result per warehouse: only the latest cutoff-eligible observation
        # may substantiate its availability, never an older convenient snapshot.
        latest_by_warehouse = {}
        for snap in snapshots:
            observed = datetime.fromisoformat(snap["observed_at"].replace("Z", "+00:00"))
            received = datetime.fromisoformat(snap["received_at"].replace("Z", "+00:00"))
            if observed <= cutoff and received <= cutoff and snap["product_id"] == c["product_id"]:
                key = snap["warehouse_id"]
                if key not in latest_by_warehouse or (observed, received) > latest_by_warehouse[key][0]:
                    latest_by_warehouse[key] = ((observed, received), snap["snapshot_id"])
        candidates = [r for r in candidates if latest_by_warehouse.get(r["warehouse_id"], (None,None))[1] == r["snapshot_id"]]
        return self._result({"case": c, "cutoff": cutoffs[0], "snapshots": snapshots,
                             "warehouse_eligibility": eligibility, "evidence_candidates": candidates},
                            scope={"case_id": case_id, "order_id": c["order_id"],
                                   "product_id": c["product_id"]},
                            refs=[f"fulfillment_cases/{case_id}"] +
                            [f"operational_events/{r['event_id']}" for r in events] +
                            [f"inventory_snapshots_v2/{r['snapshot_id']}" for r in snapshots],
                            temporal={"evidence_cutoff": cutoffs[0]},
                            limitations=(["NO_CASE_SNAPSHOT"] if not snapshots else []) +
                            ["Candidate observations are not transfer eligibility approval; effective policy and manager approval must be verified separately"])
