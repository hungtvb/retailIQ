"""W2-01 independent local source-routing and freshness acceptance artifact.

Tests real FastAPI routes against a disposable seeded SQLite database, while
using controlled timestamps to establish expected outcomes. Not a provider
uptime check or production source SLA.
"""
from __future__ import annotations

from contextlib import closing
from datetime import datetime, timedelta, timezone
import argparse
import json
import os
from pathlib import Path
import sqlite3
import tempfile
from unittest.mock import patch

from fastapi.testclient import TestClient
from scripts.seed import seed

SKU = "EL-003"


def _update(path: Path, sql: str, args: tuple):
    with closing(sqlite3.connect(path)) as db:
        with db:
            db.execute(sql, args)


def audit() -> dict:
    from retailiq.api import app

    cases: list[dict] = []
    def case(case_id: str, source: str, description: str, func):
        try:
            details = func()
            cases.append({"id": case_id, "source": source, "status": "PASS",
                          "description": description, "evidence": details})
        except Exception as error:
            cases.append({"id": case_id, "source": source, "status": "FAIL",
                          "description": description,
                          "reason": f"{type(error).__name__}: {str(error)[:270]}"})

    with tempfile.TemporaryDirectory(prefix="retailiq-freshness-audit-") as directory:
        root = Path(directory)
        db = root / "business.sqlite3"
        seed(db, write_support_files=False)
        env = {
            "RETAILIQ_DATA_DB": str(db),
            "RETAILIQ_CHAT_DB": str(root / "chat.sqlite3"),
            "RETAILIQ_WORKFLOW_DB": str(root / "workflows.sqlite3"),
            "RETAILIQ_MODE": "offline",
            "RETAILIQ_WORKFLOW_USE_MCP": "0",
        }
        with patch.dict(os.environ, env):
            with TestClient(app) as client:
                def post(path, data):
                    response = client.post(path, json=data)
                    assert response.status_code == 200, (
                        f"HTTP {response.status_code}: {response.text[:120]}"
                    )
                    return response.json()

                def fresh_stock():
                    timestamp = (datetime.now(timezone.utc) - timedelta(seconds=10)).isoformat()
                    _update(db, "UPDATE inventory SET updated_at=? WHERE sku=?",
                            (timestamp, SKU))
                    r = post("/api/workflows/freshness/route",
                             {"metric": "available_stock", "sku": SKU})
                    assert r["status"] == "PASS" and r["checked_records"] == 3
                    assert r["tool_execution"] == "executed_readonly"
                    return {"status": r["status"], "locations": r["checked_records"]}
                case("W2-FR-01", "inventory", "All stock locations within 15 minutes", fresh_stock)

                def one_stale():
                    timestamp = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
                    _update(db,
                            "UPDATE inventory SET updated_at=? WHERE sku=? AND location_id='ST-HN'",
                            (timestamp, SKU))
                    r = post("/api/workflows/freshness/route",
                             {"metric": "available_stock", "sku": SKU})
                    assert r["status"] == "STALE" and not r["meets_target"]
                    return {"status": r["status"], "locations": r["checked_records"]}
                case("W2-FR-02", "inventory", "One stale location invalidates aggregate", one_stale)

                def future():
                    timestamp = (datetime.now(timezone.utc) + timedelta(minutes=3)).isoformat()
                    _update(db,
                            "UPDATE inventory SET updated_at=? WHERE sku=? AND location_id='ST-HN'",
                            (timestamp, SKU))
                    r = post("/api/workflows/freshness/route",
                             {"metric": "available_stock", "sku": SKU})
                    assert r["status"] == "STALE" and "future" in r["reason"].lower()
                    return {"status": r["status"], "reason": "future_timestamp"}
                case("W2-FR-03", "inventory", "Future timestamp is invalid even with other valid locations", future)

                def live_query():
                    r = post("/api/workflows/freshness/question",
                             {"question": "What is stock of EL-003 right now?"})
                    assert r["status"] == "STALE" or r["status"] == "UNVERIFIED"
                    assert r["routes"][0]["applied_tier"] == "live"
                    assert not r["routes"][0]["meets_target"]
                    return {"status": r["status"], "applied_tier": "live"}
                case("W2-FR-04", "inventory", "Live request cannot be satisfied by SQLite snapshot", live_query)

                def revenue():
                    r = post("/api/workflows/freshness/question",
                             {"question": "Doanh thu tháng 10 năm 2026?"})
                    assert r["required_metrics"] == ["net_revenue"]
                    assert r["status"] == "UNVERIFIED"
                    assert r["routes"][0]["applied_tier"] == "hourly"
                    return {"status": r["status"], "tier": "hourly"}
                case("W2-FR-05", "orders", "Revenue routes to hourly orders but has no sync timestamp", revenue)

                def top():
                    r = post("/api/workflows/freshness/question",
                             {"question": "Top sellers hàng ngày?"})
                    assert r["required_metrics"] == ["top_sellers"]
                    assert r["routes"][0]["applied_tier"] == "daily"
                    assert r["status"] == "UNVERIFIED"
                    return {"status": r["status"], "tier": "daily"}
                case("W2-FR-06", "orders", "Top sellers routes to daily source without inventing refresh", top)

                def order():
                    r = post("/api/workflows/freshness/question",
                             {"question": "Order status for ORD-0001?"})
                    assert r["required_metrics"] == ["order_state"]
                    assert r["routes"][0]["selected_tool"] == "order_lookup"
                    assert r["routes"][0]["applied_tier"] == "live"
                    assert r["status"] == "UNVERIFIED"
                    return {"status": r["status"], "source": "orders_mcp"}
                case("W2-FR-07", "orders_mcp", "Order state is live-tier but no live change feed", order)

                def product():
                    r = post("/api/workflows/freshness/question",
                             {"question": "What is the warranty of EL-003?"})
                    assert r["required_metrics"] == ["product_knowledge"]
                    assert r["routes"][0]["selected_transport"] == "chroma"
                    assert r["status"] == "UNVERIFIED"
                    return {"status": r["status"], "source": "product_documents"}
                case("W2-FR-08", "product_documents", "Product RAG has no verified source refresh SLA", product)

                def composed():
                    r = post("/api/workflows/freshness/question",
                             {"question": "Tồn kho của top seller ngay bây giờ?"})
                    assert r["status"] == "REQUIRES_ORCHESTRATION"
                    assert r["required_metrics"] == ["available_stock", "top_sellers"]
                    assert all(x["tool_execution"] == "not_executed_by_router"
                               for x in r["routes"])
                    return {"status": r["status"], "sources": len(r["routes"])}
                case("W2-FR-09", "cross_domain", "Two required sources cannot collapse to one", composed)

                def missing():
                    r = post("/api/workflows/freshness/question",
                             {"question": "Tồn kho hiện tại là bao nhiêu?"})
                    assert r["status"] == "NEEDS_PRODUCT"
                    assert all(x["tool_execution"] == "not_executed_by_router"
                               for x in r["routes"])
                    return {"status": r["status"]}
                case("W2-FR-10", "inventory", "Stock question without a product must clarify", missing)

    passed = sum(row["status"] == "PASS" for row in cases)
    return {
        "schema_version": 1, "mode": "offline_synthetic",
        "scope": "local_readonly_sqlite_and_source_selection",
        "summary": {"pass": passed, "fail": len(cases)-passed, "total": len(cases)},
        "notice": "Checks routing policy and source timestamps on fixtures; NOT a live SLA",
        "results": cases,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--out", default="data/freshness_audit_report.json")
    args = parser.parse_args()
    result = audit()
    path = Path(args.out)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf8")
    summary = result["summary"]
    print(f"Freshness audit: {summary['pass']} PASS / {summary['fail']} FAIL / {summary['total']} total")
    for row in result["results"]:
        print(f"  {row['id']} {row['status']} {row.get('reason', '')}")
    print("Report:", path.resolve())
    return int(args.strict and summary["fail"] > 0)


if __name__ == "__main__":
    raise SystemExit(main())
