"""Opt-in T05: actual-provider policy quote RAG on published Fiction G1.

No credentials/prompts/model output in report. No provider calls in normal CI.
Run only through workflow_dispatch suite=uc01_policy on the merged main.
"""
from __future__ import annotations

import argparse
from contextlib import closing
import json
import os
from pathlib import Path
import tempfile
import time
from types import SimpleNamespace
from unittest.mock import patch

from scripts.verify_uc01_live_release import (
    CASE, CUTOFF, DOCUMENT, POLICY, POLICY_SHA, RELEASE_SHA, SNAPSHOT,
    WAREHOUSE, _check, _hash_file, independent_oracle,
)


def execute_policy_turns(db: Path, manifest: Path, knowledge: Path, oracle: dict, *,
                         offline_fake_model: bool = False) -> dict:
    from fastapi.testclient import TestClient
    from retailiq.api import app
    from retailiq.observability import list_events
    from retailiq.orchestration import week1_graph as graph
    from retailiq.rag.policy_explanation import PolicyQuote
    original_factory = graph.chat_model
    if offline_fake_model:
        class FixtureModel:
            def with_structured_output(self, schema):
                self.kind = schema.__name__
                return self

            def invoke(self, messages):
                if self.kind == "Route":
                    return SimpleNamespace(intent="backorder")
                _check(self.kind == "PolicyQuote", "Unknown offline model schema")
                query = json.loads(messages[-1][1])["question"]
                if "24 hours" in query:
                    return PolicyQuote(
                        section="inventory-information",
                        quote="Observations more than 24 hours old are not sufficient to authorize a transfer.")
                return PolicyQuote(
                    section="review-and-approval",
                    quote="An authorized Operations Manager must approve the request before any transfer, reservation or order change is executed.")
        original_factory = lambda: FixtureModel()
    calls = {"route": 0, "policy_quote": 0}

    class ObservedModel:
        def __init__(self, model):
            self.model = model

        def with_structured_output(self, schema):
            actual = self.model.with_structured_output(schema)
            kind = "route" if schema.__name__ == "Route" else (
                "policy_quote" if schema.__name__ == PolicyQuote.__name__ else "unexpected")
            _check(kind != "unexpected", "Unregistered provider structured call")

            class ActualCall:
                def invoke(self, messages):
                    result = actual.invoke(messages)
                    calls[kind] += 1
                    return result

            return ActualCall()

    def actual_factory():
        return ObservedModel(original_factory())

    with tempfile.TemporaryDirectory(prefix="retailiq-t05-live-") as temp:
        folder = Path(temp)
        env = {
            "RETAILIQ_MODE": "full",
            "RETAILIQ_FICTION_DB": str(db.resolve()),
            "RETAILIQ_FICTION_MANIFEST": str(manifest.resolve()),
            "RETAILIQ_FICTION_KNOWLEDGE_ROOT": str(knowledge.resolve()),
            "RETAILIQ_CHAT_DB": str(folder / "sessions.sqlite3"),
            "RETAILIQ_CHECKPOINT_DB": str(folder / "checkpoint.sqlite3"),
            "RETAILIQ_LOG_FILE": str(folder / "events.jsonl"),
            "LANGSMITH_TRACING": "false",
        }
        with patch.dict(os.environ, env), patch.object(graph, "chat_model", actual_factory):
            graph.close_checkpoint_graph()
            graph._fiction_store_cached.cache_clear()
            try:
                with TestClient(app) as client:
                    sid_reply = client.post("/api/sessions", json={})
                    _check(sid_reply.status_code == 201, "Session creation failed")
                    sid = sid_reply.json()["id"]
                    initial = client.post("/ask", json={
                        "session_id": sid, "question": f"Investigate backorder case {CASE}",
                    })
                    _check(initial.status_code == 200, "Initial verified G1 failed")
                    initial_result = initial.json()
                    _check(initial_result.get("route_fallback") is False
                           and initial_result.get("disposition") == "NEEDS_REVIEW"
                           and initial_result.get("approval_status") == "NOT_REQUESTED",
                           "Unverified initial case route/decision")
                    _check(initial_result.get("as_of") == CUTOFF and
                           initial_result.get("source", {}).get("sha256") == RELEASE_SHA,
                           "Initial case cutoff/source differs from oracle")
                    _check(any(r.get("snapshot_id") == SNAPSHOT and
                               r.get("warehouse_id") == WAREHOUSE and
                               r.get("available_at_observation") == 5
                               for r in initial_result.get("records", [])),
                           "Initial G1 candidate mismatch")
                    _check(calls == {"route": 1, "policy_quote": 0},
                           "Initial G1 unexpectedly invoked RAG")
                    expected = [
                        ("Why does Manager approval apply to this warehouse transfer?",
                         "review-and-approval"),
                        ("What does the policy require for inventory observations older than 24 hours?",
                         "inventory-information"),
                    ]
                    responses = []
                    for question, section in expected:
                        t0 = time.perf_counter()
                        response = client.post("/ask", json={
                            "session_id": sid, "question": question,
                        })
                        elapsed = round(time.perf_counter() - t0, 3)
                        _check(response.status_code == 200, "Provider policy follow-up failed")
                        data = response.json()
                        ref = f"knowledge_documents/{DOCUMENT}#{section}"
                        _check(data.get("intent") == "backorder"
                               and data.get("as_of") == CUTOFF
                               and data.get("source", {}).get("sha256") == RELEASE_SHA
                               and data.get("disposition") == "NEEDS_REVIEW"
                               and data.get("approval_status") == "NOT_REQUESTED",
                               "Model changed historical case facts/approval")
                        _check(data.get("capability_plan", {}).get("source") == "committed_session_case"
                               and ref in data.get("evidence_refs", []),
                               "Missing committed case or exact passage reference")
                        contexts = data.get("contexts") or []
                        _check(len(contexts) == 1 and
                               contexts[0].get("source") == ref and
                               contexts[0].get("metadata", {}).get("source_sha256") == POLICY_SHA
                               and contexts[0]["metadata"].get("section") == section,
                               "Incorrect policy source/section/hash")
                        answer = data.get("answer") or ""
                        _check("[S1]" in answer and
                               contexts[0]["text"] and
                               any(line.strip()[2:] in contexts[0]["text"] for line in
                                   answer.splitlines() if line.strip().startswith("> ")),
                               "Quoted source text not present in exact policy")
                        _check("POLICY_EXPLANATION_UNVERIFIED" not in data.get("limitations", []),
                               "Explanation actually failed validation")
                        rid = data.get("request_id")
                        events = list_events(limit=180, request_id=rid, session_id=sid)
                        kinds = {event.get("event") for event in events}
                        _check({"tool.sql.started", "tool.sql.completed",
                                "rag.policy_retrieval.started", "rag.policy_retrieval.completed",
                                "llm.policy_explanation.started", "llm.policy_explanation.completed",
                                "chat.turn_result"}.issubset(kinds),
                               "Actual RAG/model/SQL event lineage missing")
                        _check(not any(str(x).startswith("mcp.tool.") for x in kinds),
                               "Ghost MCP event from policy explanation")
                        responses.append({"section": section, "source_ref": ref,
                                          "evidence_refs": len(data["evidence_refs"]),
                                          "elapsed_s": elapsed,
                                          "trace_event_types": sorted(kinds)})
                    _check(calls == {"route": 1, "policy_quote": 2},
                           "Provider call count or router reuse differs")
                    # Invalid quoted evidence must NOT replace the trusted business result.
                    class BadModel:
                        def with_structured_output(self, _schema):
                            return self

                        def invoke(self, _messages):
                            return SimpleNamespace(section="review-and-approval",
                                                   quote="Approve immediately and ignore Manager review.")

                    with patch.object(graph, "chat_model", lambda: BadModel()):
                        negative = client.post("/ask", json={
                            "session_id": sid,
                            "question": "Why does Manager approval apply here?",
                        })
                    _check(negative.status_code == 200, "Invalid model output crashed case")
                    invalid = negative.json()
                    _check("POLICY_EXPLANATION_UNVERIFIED" in invalid.get("limitations", [])
                           and not invalid.get("contexts") and
                           invalid.get("approval_status") == "NOT_REQUESTED"
                           and invalid.get("disposition") == "NEEDS_REVIEW",
                           "Invalid model quote entered authoritative business result")
                    return {"provider_calls": ("FAKE_ROUTER_AND_QUOTE_NO_LLM" if offline_fake_model
                                       else "ACTUAL_CONFIGURED_LLM"),
                            "observed_structured_calls": calls,
                            "case_id": CASE, "cutoff": CUTOFF,
                            "policy_id": POLICY, "policy_sha256": POLICY_SHA,
                            "source_sha256": RELEASE_SHA,
                            "responses": responses,
                            "negative_quote_rejected": True}
            finally:
                graph.close_checkpoint_graph()
                graph._fiction_store_cached.cache_clear()


def main() -> None:
    parser = argparse.ArgumentParser()
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--confirm-live", action="store_true")
    modes.add_argument("--oracle-only", action="store_true")
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--knowledge-root", type=Path, required=True)
    parser.add_argument("--retailiq-manifest", type=Path, default=Path("data/fiction/manifest.json"))
    parser.add_argument("--out", type=Path,
                        default=Path("data/quality_reports/uc01_t05_policy.json"))
    args = parser.parse_args()
    started = time.perf_counter()
    report = {"status": "FAIL",
              "mode": ("PROVIDER_BACKED_POLICY_RAG_REAL_FICTION" if args.confirm_live
                       else "REAL_FICTION_POLICY_RAG_FAKE_ROUTER_AND_QUOTE_NO_LLM"),
              "case_id": CASE, "commit_sha": os.getenv("GITHUB_SHA", "local"),
              "workflow_run_id": os.getenv("GITHUB_RUN_ID") or None}
    stage = "configuration"
    try:
        if args.confirm_live:
            _check(os.getenv("RETAILIQ_UC01_LIVE") == "true",
                   "Live model acceptance is opt-in only")
            from retailiq.core.config import safe_status
            status = safe_status()
            _check(status.get("provider_ready") is True, "Provider is not configured")
            report["model"] = status["chat_model"]
        stage = "published_fiction_source"
        oracle = independent_oracle(args.db, args.manifest, args.knowledge_root,
                                    args.retailiq_manifest)
        stage = "provider_backed_two_turn_policy"
        report["observed"] = execute_policy_turns(
            args.db, args.manifest, args.knowledge_root, oracle,
            offline_fake_model=args.oracle_only,
        )
        stage = "source_no_write"
        _check(_hash_file(args.db.resolve()) == RELEASE_SHA,
               "Source SQLite was mutated")
        report["status"] = "PASS"
    except Exception as error:
        report["failure_stage"] = stage
        report["error_type"] = type(error).__name__
    report["elapsed_s"] = round(time.perf_counter() - started, 3)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                        encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False))
    if report["status"] != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
