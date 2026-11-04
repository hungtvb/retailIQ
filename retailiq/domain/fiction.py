"""Reviewed, read-only business queries for the unified Fiction Retail snapshot.

Use ``FictionStore.open`` after verifying the manifest, never the legacy demo DB.
These functions return scoped *facts*, not business approvals or live telemetry.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from contextlib import closing
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from hashlib import sha256
import json
from pathlib import Path
import re
import sqlite3
from uuid import UUID
from types import MappingProxyType

from retailiq.infrastructure.sqlite import query

RELEASE = "fiction-retail-unified-v1.0.0"
_UUID = re.compile(r"^[a-fA-F0-9]{8}-(?:[a-fA-F0-9]{4}-){3}[a-fA-F0-9]{12}$")
_SKU = re.compile(r"^FR-[0-9A-F]{16}$")
_LIMIT = 100
_VERIFIED_CONSTRUCTION = object()


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
    try:
        result = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise FictionDataError("Invalid financial amount") from exc
    if not result.is_finite() or result < 0:
        raise FictionDataError("Invalid financial amount")
    return result


def _file_identity(path: Path) -> tuple[int, int, int, int]:
    """Cheap change detector after one full release hash; not tamper-proof auth."""
    try:
        stat = path.stat()
    except OSError as exc:
        raise FictionDataError("Verified Fiction snapshot is unavailable") from exc
    return stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns


def _require_single_file_snapshot(path: Path) -> None:
    """Reject WAL sidecars: the release hash covers only the main SQLite file.

    Read-only SQLite connections still see committed WAL pages, which may differ
    from the pinned main-file checksum. The released Fiction DB is DELETE-mode.
    """
    for suffix in ("-wal", "-shm"):
        if path.with_name(path.name + suffix).exists():
            raise FictionDataError("Fiction snapshot has an unverified SQLite WAL sidecar")


def _aware_timestamp(raw: str) -> datetime:
    try:
        value = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except (ValueError, AttributeError, TypeError) as exc:
        raise FictionDataError("Invalid Fiction evidence timestamp") from exc
    if value.tzinfo is None or value.utcoffset() is None:
        raise FictionDataError("Unqualified timezone in Fiction evidence")
    return value


def _usd(value: Decimal) -> str:
    return str(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def verify_release(db_path: str | Path, manifest_path: str | Path) -> dict:
    """Fail closed if bytes, schema, manifest and immutable identity diverge."""
    db_path, manifest_path = Path(db_path).resolve(), Path(manifest_path).resolve()
    if not db_path.is_file() or not manifest_path.is_file():
        raise FictionDataError("Fiction SQLite and release manifest are both required")
    _require_single_file_snapshot(db_path)
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
        if conn.execute("PRAGMA journal_mode").fetchone()[0].lower() != "delete":
            raise FictionDataError("Fiction release requires DELETE journal mode, not WAL")
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
    _require_single_file_snapshot(db_path)
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

    def __init__(self, db_path: str | Path, release: dict, *, _token: object = None):
        if _token is not _VERIFIED_CONSTRUCTION:
            raise FictionDataError("Use FictionStore.open() to verify the release")
        self.db_path = Path(db_path).resolve()
        self.release = MappingProxyType(dict(release))
        self._snapshot_identity = _file_identity(self.db_path)

    @classmethod
    def open(cls, db_path: str | Path, manifest_path: str | Path) -> "FictionStore":
        # Hash full SQLite only once per store instance, not once per query.
        path = Path(db_path).resolve()
        before = _file_identity(path)
        release = verify_release(path, manifest_path)
        if before != _file_identity(path):
            raise FictionDataError("Fiction snapshot changed during release verification")
        return cls(path, release, _token=_VERIFIED_CONSTRUCTION)

    def _q(self, sql: str, args: tuple = ()) -> list[dict]:
        _require_single_file_snapshot(self.db_path)
        if _file_identity(self.db_path) != self._snapshot_identity:
            raise FictionDataError("Fiction snapshot changed since release verification")
        rows = query(sql, args, db_path=self.db_path)
        _require_single_file_snapshot(self.db_path)
        if _file_identity(self.db_path) != self._snapshot_identity:
            raise FictionDataError("Fiction snapshot changed during SQL query")
        return rows

    def _result(self, data: object, *, scope: dict, refs: list[str],
                temporal: dict | None = None, limitations: list[str] | None = None,
                aggregate_evidence: dict | None = None) -> dict:
        notices = list(limitations or [])
        if len(refs) > _LIMIT:
            notices.append("RECORD_REFS_TRUNCATED: only the first 100 source references are shown")
        result = {
            "data": data,
            "source": {"id": "fiction-retail/sqlite", "version": self.release["pack_version"],
                       "sha256": self.release["runtime_sha256"]},
            "scope": scope, "record_refs": refs[:_LIMIT],
            "temporal": temporal or {"dataset_business_as_of": self.release["dataset_business_as_of"]},
            "limitations": notices,
        }
        if aggregate_evidence is not None:
            result["aggregate_evidence"] = aggregate_evidence
        return result

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
        """Verified, bounded order facts; shipment state is release-recorded, not historic at case cutoff."""
        oid = _id(order_id)
        orders = self._q("SELECT order_id, order_date, order_status, total_amount "
                         "FROM orders WHERE order_id=?", (oid,))
        if not orders:
            return self._result(None, scope={"order_id": oid}, refs=[], limitations=["ORDER_NOT_FOUND"])
        if len(orders) != 1 or _id(orders[0]["order_id"]) != oid:
            raise FictionDataError("Inconsistent order identity")
        _money(orders[0]["total_amount"])
        lines = self._q("SELECT order_item_id, order_id, product_id, quantity, unit_price, discount_pct "
                        "FROM order_items WHERE order_id=? ORDER BY order_item_id LIMIT ?", (oid, _LIMIT + 1))
        shipments = self._q("SELECT shipment_id, order_id, warehouse_id, shipped_date, delivered_date, shipment_state "
                            "FROM shipments WHERE order_id=? ORDER BY shipment_id LIMIT ?", (oid, _LIMIT + 1))
        if 1 + len(lines) + len(shipments) > _LIMIT:
            raise FictionDataError("Order detail exceeds bounded response limit")
        line_ids: set[str] = set()
        product_ids: set[str] = set()
        for line in lines:
            lid = _id(line.pop("order_item_id"))
            if lid in line_ids or _id(line.pop("order_id")) != oid:
                raise FictionDataError("Duplicate or mismatched order line")
            line_ids.add(lid)
            line["order_item_id"] = lid
            pid = _id(line["product_id"])
            product_ids.add(pid)
            line["product_id"] = pid
            if type(line["quantity"]) is not int or line["quantity"] <= 0:
                raise FictionDataError("Invalid order line quantity")
            _money(line["unit_price"])
            if type(line["discount_pct"]) is not int or not 0 <= line["discount_pct"] <= 100:
                raise FictionDataError("Invalid order line discount")
        if product_ids:
            placeholders = ",".join("?" for _ in product_ids)
            known = self._q("SELECT product_id FROM products WHERE product_id IN ("
                            + placeholders + ")", tuple(sorted(product_ids)))
            if {row["product_id"] for row in known} != product_ids:
                raise FictionDataError("Order line references unknown product")
        shipment_ids: set[str] = set()
        warehouse_ids: set[str] = set()
        for shipment in shipments:
            sid = _id(shipment.pop("shipment_id"))
            if sid in shipment_ids or _id(shipment.pop("order_id")) != oid:
                raise FictionDataError("Duplicate or mismatched shipment")
            shipment_ids.add(sid)
            shipment["shipment_id"] = sid
            shipment["warehouse_id"] = _id(shipment["warehouse_id"])
            warehouse_ids.add(shipment["warehouse_id"])
        if warehouse_ids:
            placeholders = ",".join("?" for _ in warehouse_ids)
            known = self._q("SELECT warehouse_id FROM warehouses WHERE warehouse_id IN ("
                            + placeholders + ")", tuple(sorted(warehouse_ids)))
            if {row["warehouse_id"] for row in known} != warehouse_ids:
                raise FictionDataError("Shipment references unknown warehouse")
        return self._result({"order": orders[0], "lines": lines, "shipments": shipments},
                            scope={"order_id": oid}, refs=[f"orders/{oid}"] +
                            [f"order_items/{r['order_item_id']}" for r in lines] +
                            [f"shipments/{r['shipment_id']}" for r in shipments],
                            temporal={"order_date": orders[0]["order_date"],
                                      "dataset_business_as_of": self.release["dataset_business_as_of"]},
                            limitations=["Order/shipment state is release-recorded, NOT state at a historical case cutoff; payment settlement and live delivery remain unverified"])

    def inventory(self, product: str, warehouse_id: str | None = None) -> dict:
        """Undated base inventory, never case-cutoff or live-stock evidence."""
        pid = self.resolve_product(product)
        wid = _id(warehouse_id) if warehouse_id is not None else None
        scope = {"requested_product": product, "product_id": pid, "warehouse_id": wid}
        if pid is None:
            return self._result([], scope=scope, refs=[], limitations=["PRODUCT_NOT_FOUND"])
        # Real unified Fiction release contains a warehouses master. A missing
        # warehouse must not masquerade as a stock-record absence.
        if wid is not None:
            known_warehouse = self._q("SELECT warehouse_id FROM warehouses WHERE warehouse_id=?", (wid,))
            if not known_warehouse:
                return self._result([], scope=scope, refs=[], limitations=["WAREHOUSE_NOT_FOUND"])
        rows = self._q("SELECT inventory_id, product_id, warehouse_id, quantity_on_hand, "
                       "reserved_quantity, last_restocked_date FROM inventory "
                       "WHERE product_id=? AND (? IS NULL OR warehouse_id=?) ORDER BY warehouse_id LIMIT ?",
                       (pid, wid, wid, _LIMIT + 1))
        if len(rows) > _LIMIT:
            raise FictionDataError("Inventory result exceeds bounded response limit")
        seen: set[str] = set()
        for row in rows:
            iid = _id(row["inventory_id"])
            if iid in seen or _id(row["product_id"]) != pid or _id(row["warehouse_id"]) != row["warehouse_id"]:
                raise FictionDataError("Mismatched inventory scope or duplicate inventory ID")
            if wid and row["warehouse_id"] != wid:
                raise FictionDataError("Inventory returned wrong warehouse")
            seen.add(iid)
            on_hand, reserved = row["quantity_on_hand"], row["reserved_quantity"]
            if type(on_hand) is not int or type(reserved) is not int or not 0 <= reserved <= on_hand:
                raise FictionDataError("Invalid stock evidence")
            row["available_snapshot"] = on_hand - reserved
        return self._result(rows, scope=scope,
                            refs=[f"inventory/{r['inventory_id']}" for r in rows],
                            limitations=["UNDATED_INVENTORY: snapshot time unknown; not current or historical-at-query-period stock"]
                            + (["NO_INVENTORY_RECORDS: not equivalent to zero stock"] if not rows else []))

    def top_sellers(self, month: str, limit: int = 5) -> dict:
        first, end = _period(month)
        if type(limit) is not int or not 1 <= limit <= 20:
            raise ValueError("Top-seller limit must be 1..20")
        rows = self._q("SELECT oi.product_id, p.sku, SUM(oi.quantity) AS delivered_units, "
                       "COUNT(oi.order_item_id) AS contributing_order_lines "
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
                            aggregate_evidence={
                                "kind": "derived_sql_aggregate",
                                "source_tables": ["orders", "order_items", "products"],
                                "joins": ["orders.order_id = order_items.order_id",
                                          "order_items.product_id = products.product_id"],
                                "measure": "SUM(order_items.quantity)",
                                "contributor_count": "COUNT(order_items.order_item_id)",
                                "group_by": ["order_items.product_id", "products.sku"],
                                "order_by": ["delivered_units DESC", "order_items.product_id ASC"],
                                "filters": {"order_status": "delivered", "order_date_from": first,
                                            "order_date_to_exclusive": end},
                                "record_refs_role": "product_identity_only",
                            },
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
        item_net = Decimal(0)
        for line in lines:
            if type(line["quantity"]) is not int or line["quantity"] <= 0:
                raise FictionDataError("Invalid returned product line quantity")
            if type(line["discount_pct"]) is not int or not 0 <= line["discount_pct"] <= 100:
                raise FictionDataError("Invalid returned product line discount")
            item_net += (Decimal(line["quantity"]) * _money(line["unit_price"]) *
                         (Decimal(100 - line["discount_pct"]) / Decimal(100)))
        refund_value = _money(entry["refund_amount"])
        order_value = _money(entry["total_amount"])
        # No matching line is MISSING EVIDENCE, not financial zero.
        entry["returned_product_lines_net_usd"] = _usd(item_net) if lines else None
        entry["refund_above_order_value"] = refund_value > order_value
        entry["refund_above_returned_product_lines"] = (refund_value > item_net) if lines else None
        return self._result(entry, scope={"return_id": rid, "order_id": entry["order_id"],
                                          "product_id": entry["product_id"]},
                            refs=[f"returns/{rid}", f"orders/{entry['order_id']}"] +
                            [f"order_items/{r['order_item_id']}" for r in lines],
                            temporal={"return_date": entry["return_date"]},
                            limitations=["Recorded refund amount is not evidence of approved or completed payment"] +
                            (["NO_MATCHING_ORDER_LINE: product-line comparison unavailable"] if not lines else
                             ["Returned product lines may exceed the individually returned quantity"] ))

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
        cutoff = _aware_timestamp(cutoffs[0])
        snapshots = self._q("SELECT snapshot_id, product_id, warehouse_id, observed_at, received_at, "
                            "on_hand, reserved FROM inventory_snapshots_v2 WHERE case_id=? "
                            "ORDER BY observed_at, snapshot_id", (case_id,))
        eligibility = self._q("SELECT warehouse_id, eligible, reason_code FROM warehouse_eligibility "
                              "WHERE case_id=? ORDER BY warehouse_id", (case_id,))
        routes = {r["warehouse_id"]: r for r in eligibility}
        if type(c["request_qty"]) is not int or c["request_qty"] <= 0:
            raise FictionDataError("Invalid case requested quantity")
        for route in eligibility:
            if type(route["eligible"]) is not int or route["eligible"] not in (0, 1):
                raise FictionDataError("Invalid warehouse route eligibility")

        # Rank observations at or before the cutoff; a newer but insufficient
        # observation supersedes an older and more convenient observation.
        latest_by_warehouse: dict[str, tuple[tuple[datetime, datetime, str], str]] = {}
        for snap in snapshots:
            observed = _aware_timestamp(snap["observed_at"])
            received = _aware_timestamp(snap["received_at"])
            if type(snap["on_hand"]) is not int or type(snap["reserved"]) is not int or not 0 <= snap["reserved"] <= snap["on_hand"]:
                raise FictionDataError("Invalid case-scoped inventory quantities")
            if received < observed:
                raise FictionDataError("Snapshot received before it was observed")
            if snap["product_id"] == c["product_id"] and observed <= cutoff and received <= cutoff:
                key = snap["warehouse_id"]
                rank = (observed, received, snap["snapshot_id"])
                if key not in latest_by_warehouse or rank > latest_by_warehouse[key][0]:
                    latest_by_warehouse[key] = (rank, snap["snapshot_id"])

        candidates = []
        gap_reasons = set()
        for snap in snapshots:
            observed, received = _aware_timestamp(snap["observed_at"]), _aware_timestamp(snap["received_at"])
            reasons = []
            warehouse = snap["warehouse_id"]
            if snap["product_id"] != c["product_id"]:
                reasons.append("WRONG_PRODUCT")
            if observed > cutoff:
                reasons.append("OBSERVED_AFTER_CUTOFF")
            if received > cutoff:
                reasons.append("RECEIVED_AFTER_CUTOFF")
            if observed <= cutoff and cutoff - observed > timedelta(hours=24):
                reasons.append("STALE_OBSERVATION")
            if warehouse == c["assigned_warehouse_id"]:
                reasons.append("ASSIGNED_WAREHOUSE_NOT_ALTERNATIVE")
            route = routes.get(warehouse)
            if route is None:
                reasons.append("WAREHOUSE_ROUTE_UNKNOWN")
            elif route["eligible"] != 1:
                reasons.append("WAREHOUSE_ROUTE_INELIGIBLE")
            available = snap["on_hand"] - snap["reserved"]
            if available < c["request_qty"]:
                reasons.append("INSUFFICIENT_AVAILABLE")
            latest = latest_by_warehouse.get(warehouse)
            if (snap["product_id"] == c["product_id"] and observed <= cutoff and received <= cutoff and
                latest and latest[1] != snap["snapshot_id"]):
                reasons.append("SUPERSEDED_BY_NEWER_OBSERVATION")
            snap["available_at_observation"] = available
            snap["candidate_eligible"] = not reasons
            snap["exclusion_reasons"] = reasons
            gap_reasons.update(reasons)
            if not reasons:
                candidates.append({"snapshot_id": snap["snapshot_id"],
                                   "warehouse_id": warehouse,
                                   "available_at_observation": available})
        limitations = (["NO_CASE_SNAPSHOT"] if not snapshots else [])
        if not candidates:
            limitations += ["NO_VERIFIED_ALTERNATIVE_WAREHOUSE_CANDIDATE"]
        limitations.append("Candidate observations are not transfer eligibility approval; effective policy and manager approval must be verified separately")
        return self._result({"case": c, "cutoff": cutoffs[0], "snapshots": snapshots,
                             "warehouse_eligibility": eligibility, "evidence_candidates": candidates,
                             "candidate_gap_reasons": sorted(gap_reasons)},
                            scope={"case_id": case_id, "order_id": c["order_id"],
                                   "product_id": c["product_id"],
                                   "assigned_warehouse_id": c["assigned_warehouse_id"]},
                            refs=[f"fulfillment_cases/{case_id}"] +
                            [f"operational_events/{r['event_id']}" for r in events] +
                            [f"inventory_snapshots_v2/{r['snapshot_id']}" for r in snapshots] +
                            [f"warehouse_eligibility/{case_id}/{r['warehouse_id']}" for r in eligibility],
                            temporal={"evidence_cutoff": cutoffs[0]},
                            limitations=limitations)