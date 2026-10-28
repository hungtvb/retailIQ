"""Prepare a small, reproducible manual-vs-RetailIQ business pilot.

Creates CSV exports, balanced task assignments and an independent answer key.
Does NOT measure or fabricate employee/business time savings.

Run:
  python -m scripts.business_pilot_export --output data/business_pilot_run1
Requires an existing *synthetic* retailiq SQLite DB, e.g. python -m scripts.seed.
"""
from __future__ import annotations

import argparse
import csv
from datetime import date
from hashlib import sha256
import json
from pathlib import Path
import sqlite3

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = ROOT / "data" / "retailiq.sqlite3"

TASKS = (
    ("T01", "How many units of AlphaBook Pro 14 are currently in stock?",
     "SKU, total available, available by location"),
    ("T02", "How many units of NovaPhone X are currently in stock?",
     "SKU, total available, available by location"),
    ("T03", "How many units of USB-C GaN Charger 65W are currently in stock?",
     "SKU, total available, available by location"),
    ("T04", "What is the revenue this month?",
     "Month, total net revenue VND, net revenue by channel"),
    ("T05", "Which products are top sellers?",
     "Five ranked SKUs and completed-order units sold"),
    ("T06", "Which top seller needs a replenishment review based on stock?",
     "Top SKU, completed units sold, available units, REVIEW or NO IMMEDIATE PRIORITY"),
)

PRODUCT_SKUS = ("EL-001", "EL-002", "EL-003")
PARTICIPANTS = ("P01", "P02", "P03", "P04")


def _rows(db, sql, params=()):
    return [dict(row) for row in db.execute(sql, params).fetchall()]


def _save_csv(destination: Path, fieldnames: list[str], rows):
    with destination.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames)
        writer.writeheader()
        for item in rows:
            # Never execute spreadsheet formulas from synthetic source strings.
            writer.writerow({
                key: ("'" + value if isinstance(value, str)
                      and value.lstrip().startswith(("=", "+", "@")) else value)
                for key, value in item.items()
            })


def _stock(db, sku):
    result = _rows(db, """
        SELECT p.sku, p.name, l.id AS location_id, l.name AS location_name,
               i.on_hand, i.reserved, i.on_hand-i.reserved AS available
        FROM inventory i JOIN products p ON p.sku=i.sku
        JOIN locations l ON l.id=i.location_id
        WHERE i.sku=? ORDER BY l.id
    """, (sku,))
    if not result:
        raise ValueError("Study needs complete stock evidence for " + sku)
    if any(x["on_hand"] < x["reserved"] or x["reserved"] < 0 for x in result):
        raise ValueError("Invalid inventory evidence for " + sku)
    return {"sku": sku, "name": result[0]["name"],
            "available_total": sum(x["available"] for x in result),
            "by_location": {x["location_id"]: x["available"] for x in result}}


def _sales(db, as_of):
    first = as_of.replace(day=1)
    last = (date(first.year+1, 1, 1) if first.month == 12
            else date(first.year, first.month+1, 1))
    bounds = (first.isoformat(), last.isoformat())
    revenue = _rows(db, """
        SELECT o.channel,
               SUM(li.quantity*li.unit_price_vnd-li.discount_vnd) AS net_revenue_vnd
        FROM orders o JOIN order_lines li ON li.order_id=o.id
        WHERE o.status='completed' AND o.ordered_at>=? AND o.ordered_at<?
        GROUP BY o.channel ORDER BY o.channel
    """, bounds)
    top = _rows(db, """
        SELECT li.sku, SUM(li.quantity) AS units_sold
        FROM order_lines li JOIN orders o ON o.id=li.order_id
        WHERE o.status='completed' AND o.ordered_at>=? AND o.ordered_at<?
        GROUP BY li.sku ORDER BY units_sold DESC, li.sku LIMIT 5
    """, bounds)
    if not revenue or len(top) != 5:
        raise ValueError("Study requires current-month revenue and five top sellers")
    return {"month": first.strftime("%Y-%m"), "total_vnd": sum(
            x["net_revenue_vnd"] for x in revenue),
            "channels": {x["channel"]: x["net_revenue_vnd"] for x in revenue}}, top


def _assignments():
    assignments = []
    for participant_idx, participant in enumerate(PARTICIPANTS):
        # Distinct order per participant, without showing any participant the
        # identical question twice. Two people use each method for every task.
        shift = (participant_idx * 2 + participant_idx // 3) % len(TASKS)
        ordered = TASKS[shift:] + TASKS[:shift]
        for order, (task_id, question, required_fields) in enumerate(ordered, 1):
            task_idx = next(idx for idx, task in enumerate(TASKS)
                            if task[0] == task_id)
            method = "manual" if (participant_idx + task_idx) % 2 == 0 else "retailiq"
            assignments.append({
                "participant_id": participant,
                "trial_order": order,
                "task_id": task_id,
                "method": method,
                "question": question,
                "required_fields": required_fields,
                "answer_recorded": "",
                "duration_seconds": "",
                "correct": "",
                "manual_steps": "",
                "notes": "",
            })
    return assignments


def export(db_path: Path, output_dir: Path, *, reference_date: date) -> dict:
    """Use only an explicitly acknowledged synthetic DB; never modify it.

    An existing export directory is never overwritten (protect measurements).
    """
    db_path = Path(db_path)
    output_dir = Path(output_dir)
    if not db_path.is_file():
        raise FileNotFoundError("Synthetic SQLite fixture missing: " + str(db_path))
    if output_dir.exists():
        raise FileExistsError("Use a new output folder; existing measurements are protected")
    original_checksum = sha256(db_path.read_bytes()).hexdigest()
    uri = db_path.resolve().as_uri() + "?mode=ro"
    with sqlite3.connect(uri, uri=True) as db:
        db.row_factory = sqlite3.Row
        products = _rows(db, """
            SELECT sku,name,category,price_vnd,spec FROM products ORDER BY sku
        """)
        stock = _rows(db, """
            SELECT i.sku, l.id AS location_id, l.name AS location_name,
                   i.on_hand,i.reserved,i.updated_at
            FROM inventory i JOIN locations l ON l.id=i.location_id
            ORDER BY i.sku,l.id
        """)
        sales = _rows(db, """
            SELECT o.id AS order_id,o.ordered_at,o.status,o.channel,
                   li.sku,li.quantity,li.unit_price_vnd,li.discount_vnd
            FROM orders o JOIN order_lines li ON li.order_id=o.id
            ORDER BY o.id,li.id
        """)
        if len(products) != 10 or len(stock) != 30 or not 120 <= len(sales) <= 200:
            raise ValueError("The pilot expects the 10-product / 120-order synthetic seed")
        stocks = [_stock(db, sku) for sku in PRODUCT_SKUS]
        monthly_revenue, top5 = _sales(db, reference_date)
        leader = _stock(db, top5[0]["sku"])
        conclusion = ("REVIEW" if leader["available_total"] < top5[0]["units_sold"]
                      else "NO IMMEDIATE PRIORITY")
    if sha256(db_path.read_bytes()).hexdigest() != original_checksum:
        raise RuntimeError("Source fixture changed while exporting; stop the study")
    answer_key = []
    for i, (task_id, _, _) in enumerate(TASKS):
        if i < 3:
            answer = stocks[i]
        elif i == 3:
            answer = monthly_revenue
        elif i == 4:
            answer = {"month": monthly_revenue["month"], "top5": top5}
        else:
            answer = {"month": monthly_revenue["month"], "sku": leader["sku"],
                      "units_sold": top5[0]["units_sold"],
                      "available_total": leader["available_total"],
                      "by_location": leader["by_location"],
                      "screening_outcome": conclusion,
                      "caveat": "Illustrative review heuristic; no purchase order"}
        answer_key.append({"task_id": task_id, "expected_json": json.dumps(
            answer, sort_keys=True, ensure_ascii=False)})
    assignments = _assignments()
    # Verify balanced crossover before creating any files.
    for task_id, _, _ in TASKS:
        counts = {method: sum(x["task_id"] == task_id and x["method"] == method
                              for x in assignments) for method in ("manual", "retailiq")}
        if counts != {"manual": 2, "retailiq": 2}:
            raise AssertionError("Pilot allocation is not balanced for " + task_id)
    output_dir.mkdir(parents=True, exist_ok=False)
    _save_csv(output_dir / "products.csv",
              ["sku", "name", "category", "price_vnd", "spec"], products)
    _save_csv(output_dir / "inventory.csv",
              ["sku", "location_id", "location_name", "on_hand", "reserved",
               "updated_at"], stock)
    _save_csv(output_dir / "sales.csv",
              ["order_id", "ordered_at", "status", "channel", "sku", "quantity",
               "unit_price_vnd", "discount_vnd"], sales)
    _save_csv(output_dir / "assignments_and_results.csv",
              list(assignments[0]), assignments)
    _save_csv(output_dir / "FACILITATOR_ONLY_answer_key.csv",
              ["task_id", "expected_json"], answer_key)
    manifest = {"experiment": "internal synthetic-data usability pilot",
                "reference_month": monthly_revenue["month"],
                "dataset_type": "synthetic",
                "dataset_sha256": original_checksum,
                "products": len(products), "inventory_rows": len(stock),
                "sales_lines": len(sales),
                "participants": list(PARTICIPANTS),
                "tasks": len(TASKS), "planned_trials": len(assignments),
                "real_business_benefit_verified": False,
                "real_user_observations": 0}
    (output_dir / "manifest.json").write_text(json.dumps(
        manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    return manifest


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", type=Path, default=DEFAULT_DB,
                        help="Synthetic seed DB only, never use real customer data")
    parser.add_argument("--output", type=Path,
                        default=ROOT / "data" / "business_pilot_run1")
    parser.add_argument("--as-of", default="2026-10-28")
    options = parser.parse_args()
    result = export(options.db, options.output,
                    reference_date=date.fromisoformat(options.as_of))
    print(json.dumps({"status": "READY_NOT_MEASURED",
                      "export_dir": str(options.output),
                      "manifest": result}, ensure_ascii=False))


if __name__ == "__main__":
    main()
