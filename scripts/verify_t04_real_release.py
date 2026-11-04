"""Actual 209MB Fiction Git LFS release: real MCP stdio + independent raw SQL.

Not a synthetic fixture, provider-backed LLM test, or live inventory check.
"""
from __future__ import annotations

from contextlib import closing
from hashlib import sha256
from pathlib import Path
from unittest.mock import patch
import argparse
import json
import os
import sqlite3
import time

from retailiq.domain.fiction import FictionStore, verify_release
from retailiq.mcp_adapter import read_fiction_inventory, read_fiction_order

GOLDEN_CASE = "CASE-06181249-280d-59b3-b00b-b3de7877eb59"
EXPECTED_SIZE = 209_063_936


def _digest(path: Path) -> str:
    h = sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def verify(db: Path, manifest: Path, expected_manifest: Path) -> dict:
    db, manifest = db.resolve(), manifest.resolve()
    if db.stat().st_size != EXPECTED_SIZE:
        raise ValueError("Wrong Fiction SQLite size: Git LFS pointer or release mismatch")
    release = verify_release(db, manifest)
    pinned = json.loads(expected_manifest.read_text(encoding="utf-8"))
    if (release["pack_version"] != pinned.get("pack_version") or
            release["runtime_sha256"] != pinned.get("runtime_sha256")):
        raise ValueError("Fiction release differs from RetailIQ's pinned manifest")
    original_sha = _digest(db)
    if original_sha != release["runtime_sha256"]:
        raise ValueError("Fiction binary digest mismatch")

    with closing(sqlite3.connect(db.as_uri() + "?mode=ro&immutable=1", uri=True)) as conn:
        conn.row_factory = sqlite3.Row
        stock_key = conn.execute(
            "SELECT i.product_id,p.sku,i.warehouse_id FROM inventory i "
            "JOIN products p ON p.product_id=i.product_id "
            "WHERE i.quantity_on_hand>=0 "
            "AND i.reserved_quantity BETWEEN 0 AND i.quantity_on_hand "
            "ORDER BY i.inventory_id LIMIT 1"
        ).fetchone()
        if stock_key is None:
            raise AssertionError("No valid inventory source record")
        pid, sku, wid = stock_key["product_id"], stock_key["sku"], stock_key["warehouse_id"]
        stock_rows = [dict(r) for r in conn.execute(
            "SELECT inventory_id,product_id,warehouse_id,quantity_on_hand,"
            "reserved_quantity,last_restocked_date FROM inventory "
            "WHERE product_id=? AND warehouse_id=? ORDER BY warehouse_id", (pid, wid)
        )]
        for row in stock_rows:
            row["available_snapshot"] = row["quantity_on_hand"] - row["reserved_quantity"]

        order_key = conn.execute(
            "SELECT o.order_id FROM orders o WHERE "
            "EXISTS (SELECT 1 FROM order_items i WHERE i.order_id=o.order_id) "
            "AND EXISTS (SELECT 1 FROM shipments s WHERE s.order_id=o.order_id) "
            "ORDER BY o.order_id LIMIT 1"
        ).fetchone()
        if order_key is None:
            raise AssertionError("No order with recorded lines and shipments")
        oid = order_key["order_id"]
        header = dict(conn.execute(
            "SELECT order_id,order_date,order_status,total_amount FROM orders WHERE order_id=?",
            (oid,)
        ).fetchone())
        lines = [dict(r) for r in conn.execute(
            "SELECT order_item_id,product_id,quantity,unit_price,discount_pct "
            "FROM order_items WHERE order_id=? ORDER BY order_item_id", (oid,)
        )]
        shipments = [dict(r) for r in conn.execute(
            "SELECT shipment_id,warehouse_id,shipped_date,delivered_date,shipment_state "
            "FROM shipments WHERE order_id=? ORDER BY shipment_id", (oid,)
        )]
        case = conn.execute(
            "SELECT case_id,order_id,order_item_id,product_id,request_qty "
            "FROM fulfillment_cases WHERE case_id=?", (GOLDEN_CASE,)
        ).fetchone()
        if case is None:
            raise AssertionError("UC-01 golden case missing from Fiction release")
        case = dict(case)

    historical = FictionStore.open(db, manifest).fulfillment_case(GOLDEN_CASE)
    if (historical["data"] is None or
            historical["data"]["case"]["order_id"] != case["order_id"] or
            historical["data"]["cutoff"] != "2026-10-21T11:00:00Z"):
        raise AssertionError("UC-01 golden historical case/cutoff mismatch")

    with patch.dict(os.environ, {
        "RETAILIQ_FICTION_DB": str(db),
        "RETAILIQ_FICTION_MANIFEST": str(manifest),
    }):
        started = time.perf_counter()
        observed_stock = read_fiction_inventory(sku, wid)
        observed_order = read_fiction_order(oid)
        case_order = read_fiction_order(case["order_id"])
        elapsed = round(time.perf_counter() - started, 3)

    if observed_stock["scope"]["product_id"] != pid or observed_stock["data"] != stock_rows:
        raise AssertionError("MCP inventory differs from direct read-only SQL")
    if not any("UNDATED_INVENTORY" in x for x in observed_stock["limitations"]):
        raise AssertionError("MCP stock incorrectly omits unknown freshness")
    if observed_order["data"] != {"order": header, "lines": lines, "shipments": shipments}:
        raise AssertionError("MCP order/lines/shipments differ from read-only SQL")
    if any(x["source"]["sha256"] != original_sha for x in
           (observed_stock, observed_order, case_order)):
        raise AssertionError("MCP result release SHA differs from DB digest")
    matching = [l for l in case_order["data"]["lines"]
                if l["order_item_id"] == case["order_item_id"] and
                   l["product_id"] == case["product_id"] and
                   l["quantity"] >= case["request_qty"]]
    if len(matching) != 1:
        raise AssertionError("MCP case-linked order identity/quantity mismatch")
    if _digest(db) != original_sha:
        raise AssertionError("Read-only MCP mutated the Fiction SQLite file")

    return {"mode": "REAL_FICTION_GIT_LFS_SQLITE_AND_STDIO_MCP_NO_LLM",
            "status": "PASS", "source_sha256": original_sha,
            "inventory_rows": len(stock_rows), "order_lines": len(lines),
            "shipments": len(shipments), "case_id": GOLDEN_CASE,
            "case_cutoff": historical["data"]["cutoff"],
            "mcp_real_invocations": 3, "elapsed_s": elapsed, "live_llm": False}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--retailiq-manifest", type=Path,
                        default=Path("data/fiction/manifest.json"))
    args = parser.parse_args()
    print(json.dumps(verify(args.db, args.manifest, args.retailiq_manifest)))


if __name__ == "__main__":
    main()
