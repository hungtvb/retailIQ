"""UC-01 T02 G1: real published Fiction oracle and opt-in provider-backed /ask.

Two distinct evidence modes:
  --oracle-only: exact pinned SQLite/policy + compiled graph with FAKE router; NO LLM.
  --confirm-live: same oracle plus actual ChatOpenAI/compiled LangGraph /ask.

No prompts, customer data, provider error details or credentials are reported.
Requires the published Fiction SQLite LFS object, not a mini test fixture.
"""
from __future__ import annotations

import argparse
from contextlib import closing, nullcontext
from hashlib import sha256
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import time
from types import SimpleNamespace
from unittest.mock import patch

from retailiq.domain.fiction import verify_release

CASE = "CASE-06181249-280d-59b3-b00b-b3de7877eb59"
WAREHOUSE = "bd0b4a2e-3f75-46a1-bf8a-5a82594d70a4"
SNAPSHOT = "SNAP-850016da-7ba6-594a-8532-ca23e4085e89"
CUTOFF = "2026-10-21T11:00:00Z"
OBSERVED = "2026-10-21T10:00:00Z"
RECEIVED = "2026-10-21T10:05:00Z"
POLICY = "FR-WH-2026-10-04"
DOCUMENT = "DOC-de8b393e-45d7-53f3-b1d4-9366a5d0c134"
POLICY_PATH = "policies/FR-WH-2026-10-04.md"
POLICY_SHA = "f3ff7463e67e034360fd87b35c1c71286445be0de1431009591821489bd4d9c8"
RELEASE_SHA = "015b0a84d8d93870c6facd359347f4c039bc7fc570000890c581010d0451af42"
RELEASE = "fiction-retail-unified-v1.0.0"
RELEASE_BYTES = 209_063_936


def _check(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def _hash_file(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for part in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(part)
    return digest.hexdigest()


def independent_oracle(db: Path, manifest: Path, knowledge: Path, pinned: Path) -> dict:
    """Raw parameterized SQL, never calls FictionStore business methods."""
    db, manifest, knowledge, pinned = (
        db.resolve(), manifest.resolve(), knowledge.resolve(), pinned.resolve()
    )
    _check(db.stat().st_size == RELEASE_BYTES, "LFS object size is not the pinned release")
    expected = json.loads(pinned.read_text(encoding="utf-8"))
    _check(expected.get("runtime_sha256") == RELEASE_SHA and
           expected.get("pack_version") == RELEASE, "RetailIQ manifest was unexpectedly changed")
    release = verify_release(db, manifest)
    _check(release["pack_version"] == RELEASE and release["runtime_sha256"] == RELEASE_SHA,
           "Source release identity mismatch")
    _check(_hash_file(db) == RELEASE_SHA, "Source database bytes mismatch")
    policy_file = (knowledge / POLICY_PATH).resolve()
    _check(policy_file.is_relative_to(knowledge) and policy_file.is_file(),
           "Expected warehouse policy document is missing")
    _check(_hash_file(policy_file) == POLICY_SHA, "Warehouse policy file checksum mismatch")

    with closing(sqlite3.connect(db.as_uri() + "?mode=ro&immutable=1", uri=True)) as con:
        con.row_factory = sqlite3.Row
        case_rows = con.execute(
            "SELECT case_id,order_id,order_item_id,product_id,request_qty,assigned_warehouse_id "
            "FROM fulfillment_cases WHERE case_id=?", (CASE,)
        ).fetchall()
        _check(len(case_rows) == 1, "Golden fulfillment case missing/ambiguous")
        case = dict(case_rows[0])
        _check(case["request_qty"] == 1 and case["assigned_warehouse_id"] != WAREHOUSE,
               "Golden requested quantity or alternative warehouse scope changed")
        order_rows = con.execute(
            "SELECT order_id FROM orders WHERE order_id=?", (case["order_id"],)
        ).fetchall()
        _check(len(order_rows) == 1, "Golden order reference missing")
        item_rows = con.execute(
            "SELECT order_item_id,order_id,product_id,quantity FROM order_items "
            "WHERE order_item_id=?", (case["order_item_id"],)
        ).fetchall()
        _check(len(item_rows) == 1 and
               item_rows[0]["order_id"] == case["order_id"] and
               item_rows[0]["product_id"] == case["product_id"] and
               item_rows[0]["quantity"] >= case["request_qty"],
               "Golden line/order/product identity mismatch")
        cutoff_rows = con.execute(
            "SELECT occurred_at FROM operational_events "
            "WHERE case_id=? AND event_type='evidence_cutoff_reached'", (CASE,)
        ).fetchall()
        _check(len(cutoff_rows) == 1 and cutoff_rows[0]["occurred_at"] == CUTOFF,
               "Golden case cutoff changed")
        route = con.execute(
            "SELECT warehouse_id,eligible FROM warehouse_eligibility "
            "WHERE case_id=? AND warehouse_id=?", (CASE, WAREHOUSE)
        ).fetchall()
        _check(len(route) == 1 and route[0]["eligible"] == 1,
               "Golden alternative warehouse is not route eligible")
        snapshots = con.execute(
            "SELECT snapshot_id,product_id,warehouse_id,observed_at,received_at,on_hand,reserved "
            "FROM inventory_snapshots_v2 "
            "WHERE case_id=? AND warehouse_id=? AND product_id=? "
            "AND observed_at<=? AND received_at<=? "
            "ORDER BY observed_at DESC,received_at DESC,snapshot_id DESC",
            (CASE, WAREHOUSE, case["product_id"], CUTOFF, CUTOFF)
        ).fetchall()
        _check(bool(snapshots), "No golden snapshot at cutoff")
        latest = dict(snapshots[0])
        _check(latest["snapshot_id"] == SNAPSHOT and latest["observed_at"] == OBSERVED
               and latest["received_at"] == RECEIVED and latest["on_hand"] == 6
               and latest["reserved"] == 1 and latest["on_hand"] - latest["reserved"] == 5,
               "Golden snapshot identity/freshness/quantity differs from oracle")
        policy_rows = con.execute(
            "SELECT policy_id,requires_manager_approval FROM fulfillment_policies"
        ).fetchall()
        _check(len(policy_rows) == 1 and policy_rows[0]["policy_id"] == POLICY and
               policy_rows[0]["requires_manager_approval"] == 1,
               "Exact warehouse approval authority not verified")
        doc_rows = con.execute(
            "SELECT document_id,relative_path,sha256 FROM knowledge_documents "
            "WHERE policy_id=? AND kind='business_policy'", (POLICY,)
        ).fetchall()
        _check(len(doc_rows) == 1 and doc_rows[0]["document_id"] == DOCUMENT and
               doc_rows[0]["relative_path"] == POLICY_PATH and
               doc_rows[0]["sha256"] == POLICY_SHA,
               "Policy document registry/hash mismatch")
    return {
        "case_id": CASE, "cutoff": CUTOFF, "order_id": case["order_id"],
        "order_item_id": case["order_item_id"], "product_id": case["product_id"],
        "warehouse_id": WAREHOUSE, "snapshot_id": SNAPSHOT,
        "requested": case["request_qty"], "available": 5,
        "observed_at": OBSERVED, "received_at": RECEIVED,
        "policy_id": POLICY, "document_id": DOCUMENT, "policy_sha256": POLICY_SHA,
        "release_sha256": RELEASE_SHA, "release_version": RELEASE,
    }


def check_live_result(result: dict, oracle: dict, tool_calls: list[dict],
                      events: list[dict], request_id: str, session_id: str) -> dict:
    """Fail closed on a wrong provider route, evidence or actual invocation."""
    _check(result.get("request_id") == request_id and
           result.get("session_id") == session_id, "Request/session identity mismatch")
    _check(result.get("intent") == "backorder" and
           result.get("active_agent") == "backorder_agent" and
           result.get("route_fallback") is False, "Router decision failed/fell back")
    _check(result.get("disposition") == "NEEDS_REVIEW" and
           result.get("approval_status") == "NOT_REQUESTED",
           "Business disposition or approval was invented")
    _check(result.get("as_of") == oracle["cutoff"] and
           result.get("temporal", {}).get("evidence_cutoff") == oracle["cutoff"],
           "Case cutoff was changed or omitted")
    source = result.get("source") or {}
    _check(source.get("sha256") == oracle["release_sha256"] and
           source.get("version") == oracle["release_version"] and
           source.get("id") == "fiction-retail/sqlite",
           "Business answer was not based on pinned release")
    _check(len(tool_calls) == 1 and tool_calls[0]["case_id"] == oracle["case_id"] and
           tool_calls[0]["policy_verified"] is True and
           tool_calls[0]["policy_id"] == oracle["policy_id"] and
           tool_calls[0]["document_id"] == oracle["document_id"] and
           tool_calls[0]["document_sha256"] == oracle["policy_sha256"] and
           tool_calls[0]["order_id"] == oracle["order_id"] and
           tool_calls[0]["order_item_id"] == oracle["order_item_id"] and
           tool_calls[0]["product_id"] == oracle["product_id"] and
           tool_calls[0]["cutoff"] == oracle["cutoff"],
           "Observed actual SQL capability args/policy/evidence mismatch")
    records = result.get("records")
    _check(isinstance(records, list) and any(
        isinstance(r, dict) and
        r.get("case_id") == oracle["case_id"] and
        r.get("cutoff") == oracle["cutoff"] and
        r.get("snapshot_id") == oracle["snapshot_id"] and
        r.get("warehouse_id") == oracle["warehouse_id"] and
        r.get("observed_at") == oracle["observed_at"] and
        r.get("received_at") == oracle["received_at"] and
        r.get("available_at_observation") == oracle["available"]
        for r in records
    ), "Verified final lacks the exact golden candidate")
    refs = result.get("evidence_refs")
    needed_refs = {
        "fulfillment_cases/" + oracle["case_id"],
        "inventory_snapshots_v2/" + oracle["snapshot_id"],
        "fulfillment_policies/" + oracle["policy_id"],
        "knowledge_documents/" + oracle["document_id"],
        "orders/" + oracle["order_id"],
        "order_items/" + oracle["order_item_id"],
    }
    _check(isinstance(refs, list) and needed_refs.issubset(set(refs)),
           "Required source lineage missing")
    findings = result.get("findings")
    _check(isinstance(findings, list) and any(
        isinstance(f, dict) and
        "inventory_snapshots_v2/" + oracle["snapshot_id"] in f.get("evidence_refs", []) and
        "knowledge_documents/" + oracle["document_id"] in f.get("evidence_refs", [])
        for f in findings
    ), "Golden finding does not cite exact snapshot/policy")
    _check(isinstance(result.get("limitations"), list) and
           isinstance(result.get("answer"), str) and
           result["answer"].strip() and
           oracle["warehouse_id"] in result["answer"] and
           "review" in result["answer"].lower(),
           "Final answer lacks bounded candidate/review wording")
    _check(result.get("capability_plan", {}).get("capabilities") ==
           ["fiction.backorder.investigate"] and
           result["capability_plan"].get("case_id") == oracle["case_id"],
           "Unapproved capability plan")

    _check(all(e.get("request_id") == request_id and
               e.get("session_id") == session_id for e in events),
           "Uncorrelated events mixed into execution")
    names = {e.get("event") for e in events}
    _check({"agent.routed", "tool.sql.started", "tool.sql.completed",
            "chat.turn_result"}.issubset(names) and
           "tool.sql.failed" not in names and
           not any(n.startswith("mcp.tool.") for n in names if isinstance(n, str)),
           "Missing/contradictory tool and route events")
    _check(any(e.get("event") == "agent.routed" and
               e.get("agent") == "backorder_agent" and
               e.get("route_fallback") is False for e in events),
           "No verified route event")
    _check(any(e.get("event") == "tool.sql.completed" and
               e.get("tool") == "fiction.backorder.investigate" for e in events),
           "No actual verified SQL capability completion")
    return {"intent": "backorder", "route_fallback": False,
            "disposition": "NEEDS_REVIEW", "approval_status": "NOT_REQUESTED",
            "invoked_case_id": tool_calls[0]["case_id"],
            "snapshot_id": oracle["snapshot_id"], "warehouse_id": oracle["warehouse_id"],
            "cutoff": oracle["cutoff"], "evidence_refs_verified": len(needed_refs),
            "trace_event_types": sorted(names), "request_id": request_id,
            "session_id": session_id}


def execute_golden_case(db: Path, manifest: Path, knowledge: Path, oracle: dict,
                        *, offline_fake_router: bool = False) -> dict:
    """Full source-backed API/SQL path. Provider is fake ONLY in offline mode."""
    from fastapi.testclient import TestClient
    from retailiq.api import app
    from retailiq.domain import backorder as domain
    from retailiq.observability import list_events
    from retailiq.orchestration import week1_graph as graph

    original = domain.investigate_backorder
    calls: list[dict] = []

    def observe(store, case_id, *, knowledge_root):
        # Never log raw business data, customer details or prompts.
        _check(Path(knowledge_root).resolve() == knowledge.resolve(),
               "Untrusted policy knowledge root")
        result = original(store, case_id, knowledge_root=knowledge_root)
        p = result["data"]["policy"] or {}
        c = result["data"]["case"]
        calls.append({
            "case_id": case_id, "order_id": c["order_id"],
            "order_item_id": c["order_item_id"], "product_id": c["product_id"],
            "cutoff": result["data"]["cutoff"],
            "policy_verified": p.get("applicable_at_cutoff") is True,
            "policy_id": p.get("policy_id"),
            "document_id": p.get("document_id"),
            "document_sha256": p.get("sha256"),
        })
        return result

    with tempfile.TemporaryDirectory(prefix="retailiq-t02-live-") as temp:
        folder = Path(temp)
        env = {
            "RETAILIQ_MODE": "full", "RETAILIQ_FICTION_DB": str(db.resolve()),
            "RETAILIQ_FICTION_MANIFEST": str(manifest.resolve()),
            "RETAILIQ_FICTION_KNOWLEDGE_ROOT": str(knowledge.resolve()),
            "RETAILIQ_CHAT_DB": str(folder / "sessions.sqlite3"),
            "RETAILIQ_CHECKPOINT_DB": str(folder / "checkpoints.sqlite3"),
            "RETAILIQ_LOG_FILE": str(folder / "events.jsonl"),
            "LANGSMITH_TRACING": "false",
        }
        class OfflineCaseRouter:
            def with_structured_output(self, schema):
                return self

            def invoke(self, messages):
                return SimpleNamespace(intent="backorder")

        router_context = (patch.object(graph, "chat_model", lambda: OfflineCaseRouter())
                          if offline_fake_router else nullcontext())
        with patch.dict(os.environ, env), patch.object(domain, "investigate_backorder", observe), router_context:
            graph.close_checkpoint_graph()
            graph._fiction_store_cached.cache_clear()
            try:
                with TestClient(app) as client:
                    session_reply = client.post("/api/sessions", json={})
                    _check(session_reply.status_code == 201, "Failed to create isolated session")
                    session = session_reply.json()["id"]
                    start = time.perf_counter()
                    response = client.post("/ask", json={
                        "session_id": session,
                        "question": "Investigate backorder case " + oracle["case_id"] +
                                    ": can another warehouse cover it at the case cutoff?",
                    })
                    elapsed = round(time.perf_counter() - start, 3)
                    _check(response.status_code == 200,
                           "Real provider/graph API failed (HTTP " + str(response.status_code) + ")")
                    result = response.json()
                    rid = result.get("request_id")
                    _check(isinstance(rid, str) and bool(rid),
                           "Request ID missing from provider-backed turn")
                    events = list_events(limit=200, request_id=rid, session_id=session)
                    checks = check_live_result(result, oracle, calls, events, rid, session)
                    checks.update({"elapsed_s": elapsed,
                                   "provider_calls": ("FAKE_ROUTER_FOR_OFFLINE_GRAPH_ONLY"
                                                      if offline_fake_router else "ACTUAL_CONFIGURED_LLM"),
                                   "observed_sql_capability_calls": len(calls)})
                    return checks
            finally:
                graph.close_checkpoint_graph()
                graph._fiction_store_cached.cache_clear()


def main() -> None:
    parser = argparse.ArgumentParser()
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--oracle-only", action="store_true")
    modes.add_argument("--confirm-live", action="store_true")
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--knowledge-root", type=Path, required=True)
    parser.add_argument("--retailiq-manifest", type=Path,
                        default=Path("data/fiction/manifest.json"))
    parser.add_argument("--out", type=Path,
                        default=Path("data/quality_reports/uc01_t02_g1.json"))
    args = parser.parse_args()
    report: dict = {
        "mode": ("PROVIDER_BACKED_REAL_FICTION_RELEASE" if args.confirm_live
                 else "REAL_FICTION_SQL_POLICY_AND_FAKE_ROUTER_GRAPH_NO_LLM"),
        "status": "FAIL", "case_id": CASE,
        "commit_sha": os.getenv("GITHUB_SHA", "local"),
        "pr_head_sha": os.getenv("RETAILIQ_PR_HEAD_SHA") or None,
        "workflow_run_id": os.getenv("GITHUB_RUN_ID") or None,
        "source_sha256_expected": RELEASE_SHA,
    }
    stage = "configuration"
    started = time.perf_counter()
    try:
        if args.confirm_live:
            _check(os.getenv("RETAILIQ_UC01_LIVE") == "true",
                   "Live provider requires explicit opt-in")
            from retailiq.config import safe_status
            status = safe_status()
            _check(status.get("provider_ready") is True,
                   "Live provider configuration missing")
            report["model"] = status["chat_model"]
        stage = "source_and_sql_policy_oracle"
        oracle = independent_oracle(
            args.db, args.manifest, args.knowledge_root, args.retailiq_manifest
        )
        report["expected_g1"] = {"case_id": CASE, "cutoff": CUTOFF,
                                  "warehouse_id": WAREHOUSE, "snapshot_id": SNAPSHOT,
                                  "available": 5, "policy_document_id": DOCUMENT,
                                  "source_sha256": RELEASE_SHA}
        report["observed_sql_policy_oracle"] = oracle
        stage = ("actual_provider_langgraph_case" if args.confirm_live
                 else "offline_fake_router_compiled_graph")
        executed = execute_golden_case(
            args.db, args.manifest, args.knowledge_root, oracle,
            offline_fake_router=not args.confirm_live
        )
        report["observed_provider_graph" if args.confirm_live else "observed_offline_graph"] = executed
        stage = "no_write_integrity"
        _check(_hash_file(args.db.resolve()) == RELEASE_SHA,
               "Read-only validation changed the published SQLite bytes")
        report["status"] = "PASS"
    except Exception as error:
        # The provider may put endpoint/credential content in error messages.
        # Report only its exception class, never message, traceback or inputs.
        report["error_type"] = type(error).__name__
        report["failure_stage"] = stage
    report["elapsed_seconds"] = round(time.perf_counter() - started, 3)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n",
                        encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False))
    if report["status"] != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
