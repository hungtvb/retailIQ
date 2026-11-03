"""Independent read-only SQL acceptance for Fiction Retail unified local release.

Oracle SQL is separate from FictionStore and executes without an LLM. All acceptance
checks explicitly raise on failure, even under ``python -O``/PYTHONOPTIMIZE.
"""
from __future__ import annotations

import argparse
from contextlib import closing
from decimal import Decimal
import json
from pathlib import Path
import sqlite3

from retailiq.domain.fiction import FictionStore, FictionDataError, verify_release


def _check(condition: bool, failure: str) -> None:
    if not condition:
        raise FictionDataError(f"Fiction independent oracle failed: {failure}")


def _oracle(db_path: Path) -> dict:
    """Independent SQL over Fiction tables; do not delegate expected values to the domain code."""
    with closing(sqlite3.connect(db_path.as_uri() + "?mode=ro", uri=True)) as conn:
        conn.row_factory = sqlite3.Row
        top = conn.execute("""
            SELECT oi.product_id, SUM(oi.quantity) units,
                   COUNT(oi.order_item_id) contributing_lines
            FROM order_items oi JOIN orders o ON o.order_id=oi.order_id
            WHERE o.order_status='delivered' AND o.order_date>='2026-10-01'
              AND o.order_date<'2026-11-01'
            GROUP BY oi.product_id ORDER BY units DESC, oi.product_id LIMIT 3
        """).fetchall()
        missing = conn.execute("""SELECT c.case_id FROM fulfillment_cases c
            WHERE NOT EXISTS (SELECT 1 FROM inventory_snapshots_v2 s WHERE s.case_id=c.case_id)
            ORDER BY c.case_id""").fetchall()
        case_ids = [r[0] for r in conn.execute("SELECT case_id FROM fulfillment_cases ORDER BY case_id")]
        anomalous = conn.execute("""SELECT r.return_id FROM returns r JOIN orders o ON o.order_id=r.order_id
            WHERE r.refund_amount > o.total_amount ORDER BY r.return_id LIMIT 1""").fetchone()
        refunds = conn.execute("""
            SELECT r.return_id, r.refund_amount, o.total_amount,
                   (SELECT SUM(oi.quantity*oi.unit_price*(100-oi.discount_pct)/100.0)
                      FROM order_items oi WHERE oi.order_id=r.order_id
                        AND oi.product_id=r.product_id) returned_line_net
            FROM returns r JOIN orders o ON o.order_id=r.order_id
            WHERE r.return_id=(SELECT MIN(r2.return_id) FROM returns r2
              JOIN orders o2 ON o2.order_id=r2.order_id
              WHERE r2.refund_amount>o2.total_amount)
        """).fetchone()
        anomalies = {
            "refunds_above_order_value": conn.execute(
                "SELECT COUNT(*) FROM returns r JOIN orders o ON o.order_id=r.order_id "
                "WHERE r.refund_amount > o.total_amount").fetchone()[0],
            "refunds_above_returned_product_lines": conn.execute(
                "SELECT COUNT(*) FROM returns r WHERE r.refund_amount > "
                "(SELECT SUM(oi.quantity*oi.unit_price*(100-oi.discount_pct)/100.0) "
                "FROM order_items oi WHERE oi.order_id=r.order_id AND oi.product_id=r.product_id)"
            ).fetchone()[0],
            "warehouses_over_nominal_capacity": conn.execute(
                "SELECT COUNT(*) FROM warehouses w WHERE w.capacity_units < "
                "(SELECT SUM(i.quantity_on_hand) FROM inventory i WHERE i.warehouse_id=w.warehouse_id)"
            ).fetchone()[0],
        }
        # Positive AND negative case oracle: independent SQL uses window selection,
        # not the procedural logic in FictionStore.fulfillment_case().
        candidates = conn.execute("""
            WITH cutoffs AS (
                SELECT case_id, MIN(occurred_at) cutoff
                FROM operational_events WHERE event_type='evidence_cutoff_reached'
                GROUP BY case_id HAVING COUNT(*)=1
            ), ranked AS (
                SELECT s.case_id,s.snapshot_id,s.warehouse_id,s.product_id,
                       s.observed_at,s.received_at,s.on_hand,s.reserved,
                       c.assigned_warehouse_id,c.product_id requested_product,c.request_qty,
                       t.cutoff,
                       ROW_NUMBER() OVER (PARTITION BY s.case_id,s.warehouse_id
                           ORDER BY julianday(s.observed_at) DESC,
                                    julianday(s.received_at) DESC,s.snapshot_id DESC) rn
                FROM inventory_snapshots_v2 s
                JOIN fulfillment_cases c ON c.case_id=s.case_id
                JOIN cutoffs t ON t.case_id=s.case_id
                WHERE s.product_id=c.product_id
                  AND julianday(s.observed_at)<=julianday(t.cutoff)
                  AND julianday(s.received_at)<=julianday(t.cutoff)
            )
            SELECT r.case_id,r.snapshot_id,r.warehouse_id,r.on_hand-r.reserved available
            FROM ranked r JOIN warehouse_eligibility we
              ON we.case_id=r.case_id AND we.warehouse_id=r.warehouse_id
            WHERE r.rn=1 AND r.warehouse_id<>r.assigned_warehouse_id
              AND we.eligible=1
              AND r.on_hand>=r.reserved AND r.reserved>=0
              AND r.on_hand-r.reserved>=r.request_qty
              AND julianday(r.cutoff)-julianday(r.observed_at)<=1
              AND julianday(r.cutoff)-julianday(r.observed_at)>=0
            ORDER BY r.case_id,r.snapshot_id
        """).fetchall()
        return {
            "top3": [dict(x) for x in top],
            "cases_without_snapshot": [x[0] for x in missing],
            "case_ids": case_ids,
            "case_candidates": [dict(x) for x in candidates],
            "refund_above_order": anomalous[0] if anomalous else None,
            "refund_example": dict(refunds) if refunds else None,
            "anomalies": anomalies,
        }


def audit(db_path: Path, manifest_path: Path) -> dict:
    # Exactly one trusted path verifies the whole database before SQL acceptance.
    source = FictionStore.open(db_path, manifest_path)
    verified = dict(source.release)
    expected = _oracle(db_path)
    quality = json.loads(manifest_path.read_text(encoding="utf-8")).get("data_quality", {})
    for name, count in expected["anomalies"].items():
        _check(quality.get(name) == count, f"manifest anomaly {name}")

    ranked = source.top_sellers("2026-10", 3)
    _check([(r["product_id"], r["delivered_units"], r["contributing_order_lines"])
            for r in ranked["data"]] ==
           [(r["product_id"], r["units"], r["contributing_lines"])
            for r in expected["top3"]], "October top-seller ranking or contributor counts")
    _check(ranked["aggregate_evidence"]["source_tables"] ==
           ["orders", "order_items", "products"], "top-seller source lineage")
    _check("PARTIAL_OR_FUTURE_PERIOD" not in ' '.join(ranked["limitations"]),
           "complete October 2026 coverage")
    _check("PARTIAL_OR_FUTURE_PERIOD" in ' '.join(source.top_sellers("2026-11")["limitations"]),
           "partial November 2026 must not be complete")

    missing = expected["cases_without_snapshot"]
    _check(bool(missing), "must exercise a real missing case")
    case = source.fulfillment_case(missing[0])
    _check(case["data"]["snapshots"] == [] and case["data"]["evidence_candidates"] == [] and
           "NO_CASE_SNAPSHOT" in case["limitations"], "missing-snapshot boundary")
    observed = []
    for cid in expected["case_ids"]:
        checked = source.fulfillment_case(cid)
        for candidate in checked["data"]["evidence_candidates"]:
            _check(candidate["warehouse_id"] != checked["data"]["case"]["assigned_warehouse_id"],
                   f"assigned warehouse returned as alternative for case {cid}")
            observed.append((cid, candidate["snapshot_id"], candidate["warehouse_id"],
                             candidate["available_at_observation"]))
        for snap in checked["data"]["snapshots"]:
            _check(snap["candidate_eligible"] == (not snap["exclusion_reasons"]),
                   f"snapshot exclusion state {snap['snapshot_id']}")
    oracle_candidates = [(r["case_id"], r["snapshot_id"], r["warehouse_id"], r["available"])
                         for r in expected["case_candidates"]]
    _check(sorted(observed) == sorted(oracle_candidates), "all 100 case cutoff/route/quantity candidates")
    _check(len(expected["case_ids"]) == json.loads(manifest_path.read_text(encoding="utf-8"))
           ["table_counts"]["fulfillment_cases"], "published fulfillment case coverage")

    example = expected["refund_example"]
    _check(example is not None, "expected recorded refund anomaly")
    returned = source.refund(example["return_id"])
    _check(returned["data"]["refund_above_order_value"] is True, "refund above order value")
    _check(returned["data"]["return_id"] == returned["scope"]["return_id"], "refund scope")
    expected_above_lines = (Decimal(str(example["refund_amount"])) >
                            Decimal(str(example["returned_line_net"]))) if example["returned_line_net"] is not None else None
    _check(returned["data"]["refund_above_returned_product_lines"] is expected_above_lines,
           "refund product line comparison")
    if example["returned_line_net"] is not None:
        _check(abs(Decimal(returned["data"]["returned_product_lines_net_usd"]) -
                   Decimal(str(example["returned_line_net"]))) <= Decimal("0.01"),
               "refund product line arithmetic")

    sku = ranked["data"][0]["sku"]
    stock = source.inventory(sku)
    _check(stock["scope"]["product_id"] == ranked["data"][0]["product_id"], "SKU to canonical ID")
    with closing(sqlite3.connect(db_path.as_uri() + "?mode=ro", uri=True)) as conn:
        conn.row_factory = sqlite3.Row
        actual_rows = [dict(x) for x in conn.execute(
            "SELECT inventory_id, product_id, warehouse_id,quantity_on_hand,reserved_quantity "
            "FROM inventory WHERE product_id=? ORDER BY warehouse_id", (stock["scope"]["product_id"],))]
    _check([(r["inventory_id"], r["warehouse_id"], r["available_snapshot"])
            for r in stock["data"]] ==
           [(r["inventory_id"], r["warehouse_id"], r["quantity_on_hand"]-r["reserved_quantity"])
            for r in actual_rows], "same-product per-warehouse inventory value")
    _check(all(term not in str(obj) for term in ("customer_id", "email", "CUSTOMER_SECRET")
               for obj in (stock, returned, case)), "no customer PII in SQL response")

    return {
        "status": "PASS", "mode": "read_only_local_fiction_sql", "release": verified,
        "oracle": {"top3": expected["top3"], "missing_case_count": len(missing),
                   "case_count": len(expected["case_ids"]),
                   "candidate_count": len(oracle_candidates),
                   "example_missing_case": missing[0],
                   "example_refund_anomaly": example["return_id"],
                   "preserved_source_anomalies": expected["anomalies"]},
        "checks": ["release_integrity", "sku_identity", "top_seller_sql_lineage",
                   "partial_month", "all_case_cutoff_candidates", "refund_line_arithmetic",
                   "refund_anomaly", "preserved_source_anomalies", "inventory_same_product",
                   "no_customer_pii"],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", type=Path, default=Path("data/fiction/fiction_retail.sqlite"))
    parser.add_argument("--manifest", type=Path, default=Path("data/fiction/manifest.json"))
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = audit(args.db.resolve(), args.manifest.resolve())
    text = json.dumps(result, indent=2, ensure_ascii=False)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text + "\n", encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
