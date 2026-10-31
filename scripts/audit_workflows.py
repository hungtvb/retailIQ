"""Scenario-based behavioral audit of four-week LOCAL RetailIQ workflow slices.

Independent SQL oracle + actual FastAPI endpoints. Not an autonomous-agent,
production-security, MCP-transport, or LLM quality evaluation.

python -m scripts.audit_workflows --strict
"""
from __future__ import annotations

from contextlib import closing
from datetime import date, datetime, timedelta, timezone
import argparse
import json
import os
from pathlib import Path
import re
import sqlite3
import tempfile
from unittest.mock import patch

from fastapi.testclient import TestClient
from scripts.seed import seed


SKU = "EL-003"
DEFAULT = {"scenario": "week4", "sku": SKU, "quantity": 2, "role": "analyst"}


def sql(db: Path, statement: str, params: tuple = ()) -> list[tuple]:
    with closing(sqlite3.connect(db)) as conn:
        return conn.execute(statement, params).fetchall()


def mutate(db: Path, statement: str, params: tuple = ()) -> None:
    with closing(sqlite3.connect(db)) as conn:
        with conn:
            conn.execute(statement, params)


def stock(db: Path) -> list[tuple]:
    return sql(db, "SELECT location_id, on_hand-reserved FROM inventory WHERE sku=? ORDER BY location_id", (SKU,))


def price(db: Path) -> int:
    return sql(db, "SELECT price_vnd FROM products WHERE sku=?", (SKU,))[0][0]


def business_snapshot(db: Path) -> dict:
    return {
        "prices": sql(db, "SELECT sku,price_vnd FROM products ORDER BY sku"),
        "stock": sql(db, "SELECT sku,location_id,on_hand,reserved,updated_at FROM inventory ORDER BY sku,location_id"),
        "orders": sql(db, "SELECT id,status FROM orders ORDER BY id"),
        "lines": sql(db, "SELECT id,order_id,sku,quantity,unit_price_vnd,discount_vnd FROM order_lines ORDER BY id"),
    }


def check_trace(run: dict) -> None:
    ids = {node["id"] for node in run["graph"]["nodes"]}
    links = {(edge["from"], edge["to"]) for edge in run["graph"]["edges"]}
    previous = None
    for event in run["events"]:
        assert event["node"] in ids, f"Event refers to unknown graph node: {event['node']}"
        assert event["status"] in ("completed", "running", "awaiting", "blocked", "failed")
        assert event.get("from") == previous, (
            f"Trace chain broken: {previous} -> {event['node']} got from={event.get('from')}"
        )
        if previous is not None:
            assert (previous, event["node"]) in links, (
                f"Graph lacks executed edge {previous} -> {event['node']}"
            )
        previous = event["node"]
    if run["status"] in ("blocked", "pending_manager"):
        assert all(e["node"] != "finalize" for e in run["events"]), (
            "Finalized before successful manager review"
        )


def run_scenario(client: TestClient, scenario: str, **updates) -> dict:
    response = client.post("/api/workflows/run", json={**DEFAULT, "scenario": scenario, **updates})
    assert response.status_code == 200, f"Workflow HTTP {response.status_code}: {response.text[:250]}"
    data = response.json()
    assert data["graph"]["execution"] == "deterministic_local_simulation"
    assert "simulation" in data["simulation_notice"].lower()
    check_trace(data)
    return data


def review(client: TestClient, run_id: str, role: str, decision: str, expected_http: int) -> dict:
    response = client.post(f"/api/workflows/runs/{run_id}/review",
                           json={"role": role, "decision": decision})
    assert response.status_code == expected_http, (
        f"Review {decision}/{role} HTTP {response.status_code}, expected {expected_http}"
    )
    if response.status_code == 200:
        check_trace(response.json())
    return response.json()


def audit() -> dict:
    results: list[dict] = []

    def case(name: str, week: str, mode: str, description: str, action) -> None:
        try:
            evidence = action()
            results.append({"id": name, "week": week, "mode": mode,
                            "status": "PASS", "description": description,
                            "evidence": evidence})
        except Exception as error:
            results.append({"id": name, "week": week, "mode": mode,
                            "status": "FAIL", "description": description,
                            "reason": f"{type(error).__name__}: {str(error)[:350]}"})

    with tempfile.TemporaryDirectory(prefix="ri-workflow-audit-") as directory:
        root = Path(directory)
        db = root/"business.sqlite3"
        seed(db, write_support_files=False, reference_date=date(2026, 10, 28))
        environment = {
            "RETAILIQ_MODE": "offline", "RETAILIQ_AS_OF": "2026-10-28",
            "RETAILIQ_DATA_DB": str(db), "RETAILIQ_CHAT_DB": str(root/"chat.sqlite3"),
            "RETAILIQ_WORKFLOW_DB": str(root/"runs.sqlite3"),
            "RETAILIQ_WORKFLOW_USE_MCP": "0",
        }
        with patch.dict(os.environ, environment):
            from retailiq.api import app
            with TestClient(app) as client:
                def week1():
                    run = run_scenario(client, "week1")
                    rows = sql(db, """SELECT li.sku,SUM(li.quantity) AS units
                       FROM order_lines li JOIN orders o ON li.order_id=o.id
                       WHERE o.status='completed' AND o.ordered_at>='2026-10-01'
                         AND o.ordered_at<'2026-11-01'
                       GROUP BY li.sku ORDER BY units DESC, li.sku LIMIT 5""")
                    for sku, units in rows:
                        assert f"{sku}: {units} units" in run["report"]
                    assert "not live LangGraph" in run["report"]
                    assert "SQLite" in run["graph"]["lineage"]["sql_tool"]["source"]
                    return {"top_skus": [sku for sku, _ in rows], "records": len(rows)}
                case("W1-REPORT-ORACLE", "week1", "offline_sql", "Top-seller report vs independent completed-order SQL", week1)

                def semantic():
                    r = client.get("/api/workflows/semantics")
                    assert r.status_code == 200
                    d = r.json()
                    assert d["metrics"]["available_stock"]["definition"].find("on_hand - reserved") >= 0
                    assert d["metrics"]["net_revenue"]["unit"] == "VND"
                    assert set(d["freshness_tiers"]) == {"live", "15_min", "hourly", "daily"}
                    assert all(not t["guaranteed"] for t in d["freshness_tiers"].values())
                    return {"tiers": list(d["freshness_tiers"])}
                case("W2-SEMANTICS", "week2", "contract", "KPI semantics and non-guaranteed freshness tiers", semantic)

                def stock_source():
                    result = run_scenario(client, "week2")
                    expect = sum(value for _, value in stock(db))
                    assert f"Stock: {expect} available" in result["report"]
                    assert "MCP network transport not exercised" in result["events"][1]["detail"]
                    assert "STALE" in result["report"]
                    return {"sku": SKU, "available": expect, "mode": "local adapter"}
                case("W2-LOCAL-STOCK", "week2", "offline_sql", "Stock from SQLite, no false MCP transport claim", stock_source)

                def fresh_complete():
                    stamp = (datetime.now(timezone.utc)-timedelta(seconds=60)).isoformat()
                    mutate(db, "UPDATE inventory SET updated_at=? WHERE sku=?", (stamp,SKU))
                    result = run_scenario(client, "week2")
                    assert "Target: 15 minutes; PASS" in result["report"]
                    return {"fresh_rows": len(stock(db))}
                case("W2-FRESH-ALL", "week2", "offline_fixture", "All inventory locations fresh -> PASS", fresh_complete)

                def fresh_mixed():
                    stamp = (datetime.now(timezone.utc)-timedelta(hours=2)).isoformat()
                    mutate(db,"UPDATE inventory SET updated_at=? WHERE sku=? AND location_id='ST-HN'", (stamp,SKU))
                    result=run_scenario(client,"week2")
                    assert "Target: 15 minutes; STALE" in result["report"], (
                        "One stale location must invalidate an all-location freshness claim"
                    )
                    return {"stale_location": "ST-HN"}
                case("W2-FRESH-MIXED", "week2", "offline_fixture", "Mixed timestamps must not pass freshness", fresh_mixed)

                def mcp_mismatch():
                    from retailiq import mcp_adapter
                    with patch.dict(os.environ, {"RETAILIQ_WORKFLOW_USE_MCP": "1"}):
                        with patch.object(mcp_adapter, "read_inventory", return_value=[]):
                            result = client.post("/api/workflows/run", json={**DEFAULT, "scenario":"week2"})
                    assert result.status_code == 422, (
                        f"Mismatched MCP stock evidence must fail closed (got {result.status_code})"
                    )
                    return {"status":result.status_code}
                case("W2-MCP-DRIFT", "week2", "mocked_mcp", "Reject mismatched MCP-vs-SQL stock evidence", mcp_mismatch)

                def mock_scope():
                    a=run_scenario(client,"week3",role="analyst")
                    m=run_scenario(client,"week3",role="manager")
                    scoped = dict(stock(db))["ST-HCM"]
                    total = sum(v for _,v in stock(db))
                    assert f"{scoped} visible units" in a["events"][2]["detail"]
                    assert f"{total} visible units" in m["events"][2]["detail"]
                    assert "simulated" in a["graph"]["lineage"]["scope_guard"]["relation"].lower() or (
                        "mock" in a["graph"]["lineage"]["scope_guard"]["relation"]
                    )
                    return {"analyst_units":scoped,"manager_units":total}
                case("W3-SCOPE", "week3", "offline_fixture", "Analyst sees one permitted store; manager all locations", mock_scope)

                def mock_price():
                    before=business_snapshot(db)
                    a=run_scenario(client,"week3")
                    discounted=price(db)*95//100
                    assert f"{discounted}" in a["report"]
                    assert a["status"]=="pending_manager"
                    assert business_snapshot(db)==before
                    return {"proposal":discounted,"status":a["status"]}
                case("W3-PRICE-GATE", "week3", "offline_sql", "Price proposal is accurate, pending and read-only", mock_price)

                def approval():
                    before=business_snapshot(db)
                    a=run_scenario(client,"week3")
                    review(client,a["id"],"analyst","approve",403)
                    done=review(client,a["id"],"manager","approve",200)
                    assert done["status"]=="approved_simulated"
                    review(client,a["id"],"manager","approve",409)
                    assert business_snapshot(db)==before
                    got=client.get("/api/workflows/runs/"+a["id"]).json()
                    assert got["events"]==done["events"]
                    return {"review_status":done["status"],"events":len(done["events"])}
                case("W3-APPROVE", "week3", "offline_api", "Denied analyst, one-shot manager approval, persistent no-write trace", approval)

                def rejection():
                    before=business_snapshot(db)
                    a=run_scenario(client,"week3")
                    done=review(client,a["id"],"manager","reject",200)
                    assert done["status"]=="rejected"
                    review(client,a["id"],"manager","reject",409)
                    assert business_snapshot(db)==before
                    return {"review_status":done["status"]}
                case("W3-REJECT", "week3", "offline_api", "Rejected proposal remains read-only and cannot be reviewed twice", rejection)

                def alert(value: int):
                    mutate(db,"UPDATE inventory SET on_hand=reserved WHERE sku=?", (SKU,))
                    mutate(db,"UPDATE inventory SET on_hand=reserved+? WHERE sku=? AND location_id='ST-HCM'",(value,SKU))
                    r=run_scenario(client,"alerts")
                    expected="ALERT" if value<20 else "NORMAL"
                    assert f"Low-stock KPI: {expected}" in r["report"]
                    assert f"Available units for {SKU}: {value}" in r["report"]
                    assert "No notifications sent" in r["events"][-1]["detail"]
                    return {"stock":value, "expected":expected}
                case("W3-ALERT-19", "week3", "offline_fixture", "19 units triggers read-only alert",lambda:alert(19))
                case("W3-ALERT-20", "week3", "offline_fixture", "20 units does not trigger alert",lambda:alert(20))

                def direct():
                    mutate(db,"UPDATE inventory SET on_hand=reserved+30 WHERE sku=?",(SKU,))
                    before=business_snapshot(db)
                    r=run_scenario(client,"week4",quantity=2)
                    assert r["status"]=="pending_manager"
                    assert len([e for e in r["events"] if e["node"]=="verification"])==1
                    assert f"list total {price(db)*2} VND" in r["report"]
                    assert "allocation ST-HCM" in r["report"] or "allocation ST-HN" in r["report"] or (
                        "allocation WH-HCM" in r["report"]
                    )
                    assert business_snapshot(db)==before
                    return {"quantity":2, "status":r["status"]}
                case("W4-SINGLE-LOCATION", "week4", "offline_fixture", "Correct stock, price and single-location draft without writes", direct)

                def split():
                    mutate(db,"UPDATE inventory SET on_hand=reserved+8 WHERE sku=?",(SKU,))
                    before=business_snapshot(db)
                    r=run_scenario(client,"week4",quantity=20)
                    checks=[e for e in r["events"] if e["node"]=="verification"]
                    assert [e["status"] for e in checks]==["running","completed"]
                    assert "ST-HCM: 8" in r["report"] and "ST-HN: 8" in r["report"] and "WH-HCM: 4" in r["report"]
                    assert f"list total {price(db)*20} VND" in r["report"]
                    assert business_snapshot(db)==before
                    return {"split_qty":20,"verified":True,"replans":1}
                case("W4-SPLIT-RETRY", "week4", "offline_fixture", "Split allocation sums to requested units, one bounded retry", split)

                def blocked():
                    mutate(db,"UPDATE inventory SET on_hand=reserved+1 WHERE sku=?",(SKU,))
                    before=business_snapshot(db)
                    r=run_scenario(client,"week4",quantity=20)
                    assert r["status"]=="blocked"
                    assert r["events"][-1]["node"]=="verification"
                    assert all(e["node"]!="manager_approval" for e in r["events"])
                    review(client,r["id"],"manager","approve",409)
                    assert business_snapshot(db)==before
                    return {"available":3,"requested":20,"status":r["status"]}
                case("W4-INSUFFICIENT", "week4", "offline_fixture", "Insufficient stock blocks proposal and manager review", blocked)

                def exact_available():
                    mutate(db,"UPDATE inventory SET on_hand=reserved WHERE sku=?",(SKU,))
                    mutate(db,"UPDATE inventory SET on_hand=reserved+20 WHERE sku=? AND location_id='ST-HCM'",(SKU,))
                    r=run_scenario(client,"week4",quantity=20)
                    assert r["status"]=="pending_manager"
                    assert "allocation ST-HCM" in r["report"]
                    assert len([e for e in r["events"] if e["node"]=="verification"])==1
                    return {"available":20,"requested":20}
                case("W4-EXACT-BOUNDARY", "week4", "offline_fixture", "Exactly enough at one location requires no split", exact_available)

                def five_roles():
                    r=run_scenario(client,"week4",quantity=2)
                    spec=[n for n in r["graph"]["nodes"] if n["kind"]=="agent"]
                    assert len(spec)==5
                    assert all(n["id"] in r["graph"]["lineage"] for n in spec)
                    assert "no agent-owned tool call" in r["graph"]["lineage"]["inventory_search_agent"]["relation"]
                    return {"specialists":[n["id"] for n in spec],"execution":r["graph"]["execution"]}
                case("W4-FIVE-ROLES-LINEAGE", "week4", "mock_only", "Five roles and source lineage, no false A2A claim", five_roles)

                def bad_inputs():
                    cases=[
                        ({**DEFAULT,"sku":"INVALID","scenario":"week4"},422),
                        ({**DEFAULT,"quantity":0},422),
                        ({**DEFAULT,"quantity":21},422),
                        ({**DEFAULT,"quantity":2.5},422),
                        ({**DEFAULT,"role":"visitor"},422),
                        ({**DEFAULT,"scenario":"unknown"},422),
                    ]
                    for payload,expected in cases:
                        response=client.post("/api/workflows/run",json=payload)
                        assert response.status_code==expected, f"{payload}: got HTTP {response.status_code}"
                    missing=client.get("/api/workflows/runs/nonexistent")
                    assert missing.status_code==404
                    return {"rejected":len(cases),"missing_http":404}
                case("W4-INVALID-INPUT", "week4", "offline_api", "Invalid SKU/quantity/role/scenario rejected without fallback", bad_inputs)

                def no_mutations():
                    before=business_snapshot(db)
                    for scenario in ("week1","week2","alerts","week3","week4"):
                        run_scenario(client,scenario)
                    assert business_snapshot(db)==before
                    return {"tables":["products","inventory","orders","order_lines"],"operations":5}
                case("CROSS-NO-BUSINESS-WRITE", "cross_week", "offline_api", "All five scenarios leave every operational table unchanged", no_mutations)

    passed=sum(r["status"]=="PASS" for r in results)
    return {
        "schema_version":1, "mode":"offline_synthetic",
        "summary":{"pass":passed,"fail":len(results)-passed,"total":len(results)},
        "coverage_notice":"Behavioral API/SQLite audit; NOT live LLM, genuine MCP handshake, RBAC, A2A or measured business impact.",
        "results":results,
    }


def main() -> int:
    parser=argparse.ArgumentParser()
    parser.add_argument("--strict",action="store_true")
    parser.add_argument("--out",default="data/workflow_audit_report.json")
    args=parser.parse_args()
    report=audit()
    path=Path(args.out)
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(report,ensure_ascii=False,indent=2,default=str)+"\n",encoding="utf8")
    summary=report["summary"]
    print(f"Workflow scenario audit: {summary['pass']} PASS / {summary['fail']} FAIL / {summary['total']} total")
    for entry in report["results"]:
        print(f"  {entry['id']:<28} {entry['status']:<4}  {entry.get('reason', '')}")
    print("Report:",path.resolve())
    return int(args.strict and summary["fail"]>0)


if __name__=="__main__":
    raise SystemExit(main())
