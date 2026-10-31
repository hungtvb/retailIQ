"""Adversarial behavioral acceptance for RetailIQ's untested edges.

Runs real FastAPI endpoints with separate seeded SQLite per scenario.
Independent SQL oracle; intentionally strict about context and refusal to guess.
python -m scripts.audit_edge_scenarios [--strict]
"""
from __future__ import annotations

from collections import defaultdict
from contextlib import closing
from datetime import date, datetime, timedelta, timezone
import argparse
import json
import os
from pathlib import Path
import sqlite3
import tempfile
from unittest.mock import patch

from fastapi.testclient import TestClient
from scripts.seed import seed
from scripts.audit_queries import Oracle

SKU = "EL-003"


def write(db: Path, statement: str, args: tuple = ()) -> None:
    with closing(sqlite3.connect(db)) as conn:
        with conn:
            conn.execute(statement, args)


def ask(client: TestClient, question: str, session: str) -> dict:
    r = client.post("/ask", json={"session_id": session, "question": question})
    assert r.status_code == 200, f"/ask HTTP {r.status_code}: {r.text[:250]}"
    return r.json()


def session(client: TestClient) -> str:
    r = client.post("/api/sessions", json={})
    assert r.status_code == 201
    return r.json()["id"]


def stock_truth(oracle: Oracle, result: dict, period: str, count: int,
                rank: int | None = None) -> dict:
    ranked = oracle.top(period, count if rank is None else max(count, rank))
    skus = [ranked[rank-1]["sku"]] if rank is not None else [item["sku"] for item in ranked]
    expected = {sku: oracle.available(sku) for sku in skus}
    actual = defaultdict(int)
    for row in result.get("records") or []:
        if isinstance(row, dict) and "sku" in row and type(row.get("available")) is int:
            actual[row["sku"]] += row["available"]
    assert result["intent"] == "stock", f"Expected stock intent: {result['intent']}"
    assert dict(actual) == expected, f"wrong SKU/stock: observed {dict(actual)}, expected {expected}"
    for sku, amount in expected.items():
        assert sku in result["answer"], f"Answer omitted SKU {sku}"
        assert str(amount) in result["answer"], f"Answer omitted available stock for {sku}"
    return {"period": period, "sku_stock": expected}


def ambiguous_result(result: dict) -> dict:
    assert not result.get("records"), (
        "Ambiguous or out-of-range reference must not silently pick a product: "
        + str([r.get("sku") for r in result.get("records", [])])
    )
    assert result.get("answer", "").strip(), "Ambiguous question must prompt for clarification"
    return {"intent": result.get("intent"), "records": 0, "answer": result["answer"][:130]}


def edge_top2(client, oracle, db):
    r = ask(client,"Tồn kho của top 2 sản phẩm bán chạy tháng 10 năm 2026?",session(client))
    return stock_truth(oracle, r, "2026-10", 2)


def edge_top3_english(client, oracle, db):
    r = ask(client,"How many units are in stock for the top 3 best sellers in October 2026?",session(client))
    return stock_truth(oracle, r, "2026-10", 3)


def edge_group_top3(client,oracle,db):
    sid = session(client)
    ask(client,"Top 3 sản phẩm bán chạy tháng 9 năm 2026?",sid)
    r = ask(client,"Tồn kho của các sản phẩm đó?",sid)
    return stock_truth(oracle,r,"2026-09",3)


def edge_rank3(client,oracle,db):
    sid=session(client)
    ask(client,"Top 3 sản phẩm bán chạy tháng 9 năm 2026?",sid)
    return stock_truth(oracle,ask(client,"Tồn kho của sản phẩm đứng thứ 3?",sid),"2026-09",3,rank=3)


def edge_rank_outside(client,oracle,db):
    sid=session(client)
    ask(client,"Top 3 sản phẩm bán chạy tháng 9 năm 2026?",sid)
    return ambiguous_result(ask(client,"Tồn kho của sản phẩm đứng thứ 4?",sid))


def edge_rank_zero(client,oracle,db):
    sid=session(client)
    ask(client,"Top 3 sản phẩm bán chạy tháng 9 năm 2026?",sid)
    return ambiguous_result(ask(client,"Tồn kho của sản phẩm đứng thứ 0?",sid))


def edge_plural_english(client,oracle,db):
    sid=session(client)
    ask(client,"Which products are top sellers?",sid)
    return stock_truth(oracle,ask(client,"What about their stock?",sid),"2026-10",5)


def edge_session_isolation(client,oracle,db):
    other=session(client)
    ask(client,"Top 3 sản phẩm bán chạy tháng 9 năm 2026?",other)
    fresh=session(client)
    r=ask(client,"Tồn kho của các sản phẩm đó?",fresh)
    return ambiguous_result(r)


def edge_named_context(client,oracle,db):
    sid=session(client)
    ask(client,"Giá của AlphaBook Pro 14 là bao nhiêu?",sid)
    r=ask(client,"Tồn kho của nó?",sid)
    expected=oracle.available("EL-001")
    rows=r["records"]
    assert rows and {row["sku"] for row in rows}=={"EL-001"}
    assert sum(row["available"] for row in rows)==expected
    return {"sku":"EL-001","available":expected}


def edge_no_inventory(client,oracle,db):
    write(db,"DELETE FROM inventory WHERE sku=?",(SKU,))
    r=client.post("/api/workflows/run",json={"scenario":"week4","sku":SKU,"quantity":1})
    assert r.status_code==200, r.text[:200]
    result=r.json()
    assert result["status"]=="blocked"
    assert "approval" not in {event["node"] for event in result["events"]}
    assert "finalize" not in {event["node"] for event in result["events"]}
    assert "BLOCKED" in result["report"]
    return {"status":"blocked","rows":0}


def edge_zero_stock(client,oracle,db):
    write(db,"UPDATE inventory SET on_hand=reserved WHERE sku=?",(SKU,))
    r=client.post("/api/workflows/run",json={"scenario":"week4","sku":SKU,"quantity":1})
    assert r.status_code==200
    assert r.json()["status"]=="blocked"
    return {"available":0,"status":"blocked"}


def edge_missing_timestamp(client,oracle,db):
    write(db,"UPDATE inventory SET updated_at=NULL WHERE sku=? AND location_id='ST-HN'",(SKU,))
    r=client.post("/api/workflows/run",json={"scenario":"week2","sku":SKU})
    assert r.status_code in (422,503), (
        "Missing source timestamp must fail closed, not report fresh stock: "
        + r.text[:220]
    )
    return {"status":r.status_code}


def edge_future_timestamp(client,oracle,db):
    future=(datetime.now(timezone.utc)+timedelta(hours=1)).isoformat()
    write(db,"UPDATE inventory SET updated_at=? WHERE sku=?",(future,SKU))
    r=client.post("/api/workflows/run",json={"scenario":"week2","sku":SKU})
    assert r.status_code==200, r.text[:220]
    assert "Target: 15 minutes; STALE" in r.json()["report"], (
        "Future inventory timestamps must not be reported fresh"
    )
    return {"status":"STALE","timestamp":"future"}


def edge_negative_price(client,oracle,db):
    write(db,"UPDATE products SET price_vnd=-1 WHERE sku=?",(SKU,))
    outcome={}
    for scenario in ("week3","week4"):
        r=client.post("/api/workflows/run",json={"scenario":scenario,"sku":SKU})
        assert r.status_code in (422,503), (
            f"Negative product price must fail closed for {scenario}, got {r.status_code}: "
            +r.text[:200]
        )
        outcome[scenario]=r.status_code
    return outcome


CASES = (
    ("CHAT-TOP2", "week1", "stock group top 2", edge_top2),
    ("CHAT-TOP3-EN", "week1", "English multi-SKU stock group", edge_top3_english),
    ("CHAT-PRONOUN-TOP3", "week1", "prior September top-3 group", edge_group_top3),
    ("CHAT-RANK3", "week1", "rank 3 uses prior September list", edge_rank3),
    ("CHAT-RANK-OUTSIDE", "week1", "rank 4 after top 3 must clarify", edge_rank_outside),
    ("CHAT-RANK-ZERO", "week1", "rank zero must clarify", edge_rank_zero),
    ("CHAT-PLURAL-EN", "week1", "plural English reference means group", edge_plural_english),
    ("CHAT-ISOLATION", "week1", "new session must not inherit previous user's SKU", edge_session_isolation),
    ("CHAT-NAMED-PRONOUN", "week1", "named SKU stays anchored", edge_named_context),
    ("W4-EMPTY-INVENTORY", "week4", "no inventory rows must block", edge_no_inventory),
    ("W4-ZERO-STOCK", "week4", "all reserved must block", edge_zero_stock),
    ("W2-NULL-TIMESTAMP", "week2", "missing source timestamp must fail closed", edge_missing_timestamp),
    ("W2-FUTURE-TIMESTAMP", "week2", "future source timestamp cannot meet SLA", edge_future_timestamp),
    ("W3-W4-NEGATIVE-PRICE", "cross_week", "invalid catalog price cannot create a proposal", edge_negative_price),
)


def run_audit() -> dict:
    results = []
    from retailiq.api import app
    for case_id, week, description, action in CASES:
        with tempfile.TemporaryDirectory(prefix="ri-edge-") as root:
            root=Path(root)
            db=root/"retail.sqlite3"
            seed(db,write_support_files=False,reference_date=date(2026,10,28))
            with patch.dict(os.environ,{
                "RETAILIQ_MODE":"offline","RETAILIQ_AS_OF":"2026-10-28",
                "RETAILIQ_DATA_DB":str(db), "RETAILIQ_CHAT_DB":str(root/"chat.sqlite3"),
                "RETAILIQ_WORKFLOW_DB":str(root/"workflow.sqlite3"),
                "RETAILIQ_CHECKPOINT_DB":str(root/"checkpoint.sqlite3"),
                "RETAILIQ_WORKFLOW_USE_MCP":"0",
            }):
                with TestClient(app) as client:
                    try:
                        evidence=action(client,Oracle(db),db)
                        results.append({"id":case_id,"week":week,"description":description,
                                        "mode":"offline_api_fixture","status":"PASS","evidence":evidence})
                    except Exception as err:
                        results.append({"id":case_id,"week":week,"description":description,
                                        "mode":"offline_api_fixture","status":"FAIL",
                                        "reason":f"{type(err).__name__}: {str(err)[:380]}"})
    p=sum(x["status"]=="PASS" for x in results)
    return {"schema_version":1, "mode":"offline_synthetic",
            "summary":{"pass":p,"fail":len(results)-p,"total":len(results)},
            "notice":"Independent SQL/HTTP checks; not live LLM, secure RBAC or autonomous A2A.",
            "results":results}


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--strict",action="store_true")
    parser.add_argument("--out",default="data/edge_scenario_audit.json")
    args=parser.parse_args()
    result=run_audit()
    path=Path(args.out)
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf8")
    s=result["summary"]
    print(f"Edge scenario audit: {s['pass']} PASS / {s['fail']} FAIL / {s['total']} total")
    for case in result["results"]:
        print(f"  {case['id']:<26} {case['status']} {case.get('reason','')}")
    print("Report:",path.resolve())
    return int(args.strict and s["fail"])


if __name__=="__main__":
    raise SystemExit(main())
