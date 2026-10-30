"""W2-06: reproducible source reliability report from independent audit artifacts.

Combines ONLY measured scenarios, never invents live LLM/MCP/embedding quality,
freshness guarantees or customer experience uplift. Strictly validates source
report summaries before aggregation.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import datetime, timezone
import json
from pathlib import Path

SCENARIO_DOMAINS = {
    "catalog": ("catalog",),
    "sales": ("orders",),
    "stock": ("inventory",),
    "cross_domain": ("orders", "inventory"),
    "context": ("conversation_context",),
    "product": ("product_knowledge",),
}


def _checked_rows(report: dict, label: str) -> list[dict]:
    if not isinstance(report, dict) or not isinstance(report.get("results"), list):
        raise ValueError(f"{label}: missing result rows")
    rows = report["results"]
    if not rows or any(not isinstance(x, dict) or
                       x.get("status") not in ("PASS", "FAIL", "ERROR")
                       for x in rows):
        raise ValueError(f"{label}: malformed or empty result rows")
    summary = report.get("summary", {})
    actual = {
        "pass": sum(x["status"] == "PASS" for x in rows),
        "fail": sum(x["status"] == "FAIL" for x in rows),
        "error": sum(x["status"] == "ERROR" for x in rows),
    }
    if any(actual[key] != summary.get(key, 0) for key in actual):
        raise ValueError(f"{label}: summary differs from underlying results")
    if summary.get("total", len(rows)) != len(rows):
        raise ValueError(f"{label}: result count mismatch")
    return rows


def build_reliability_report(
    queries: dict,
    workflows: dict,
    edges: dict,
    retrieval: dict | None = None,
) -> dict:
    query_rows = _checked_rows(queries, "business_queries")
    workflow_rows = _checked_rows(workflows, "workflows")
    edge_rows = _checked_rows(edges, "adversarial_edges")
    if queries.get("mode") != "offline" or workflows.get("mode") != "offline_synthetic" or edges.get("mode") != "offline_synthetic":
        raise ValueError("Only labeled offline fixture audits may enter this report")

    source_results = defaultdict(list)
    for row in query_rows:
        group = row.get("group")
        if group not in SCENARIO_DOMAINS:
            raise ValueError("Unknown business question group")
        for source in SCENARIO_DOMAINS[group]:
            source_results[source].append(row["status"])

    def sample_quality(statuses):
        n = len(statuses)
        return {"cases": n,
                "pass": sum(x == "PASS" for x in statuses),
                "fail": sum(x == "FAIL" for x in statuses),
                "error": sum(x == "ERROR" for x in statuses),
                "pass_fraction": round(sum(x == "PASS" for x in statuses) / n, 4)}

    retrieval_summary = {
        "status": "NOT_MEASURED",
        "note": "Actual provider and embeddings retrieval metrics not supplied",
    }
    if retrieval is not None:
        if retrieval.get("evaluation_mode") != "live_provider_embeddings_and_chroma":
            raise ValueError("Retrieval report must declare real provider mode")
        strategies = retrieval.get("strategies")
        if not isinstance(strategies, dict) or not all(
            isinstance(strategies.get(key), dict)
            and isinstance(strategies[key].get("summary"), dict)
            and isinstance(strategies[key].get("per_source"), dict)
            for key in ("vector", "hybrid")
        ):
            raise ValueError("Retrieval report must contain vector and hybrid results")
        retrieval_summary = {
            "status": "PROVIDER_REPORTED_NOT_INDEPENDENTLY_VERIFIED",
            "top_k": retrieval.get("top_k"),
            "strategies": {
                name: {"summary": strategies[name]["summary"],
                       "per_source": strategies[name]["per_source"]}
                for name in ("vector", "hybrid")
            },
        }

    return {
        "report_type": "retailiq_source_reliability",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "execution_mode": "offline_synthetic_with_optional_external_retrieval",
        "sources": {name: sample_quality(statuses)
                    for name, statuses in sorted(source_results.items())},
        "test_suites": {
            "business_queries": sample_quality([r["status"] for r in query_rows]),
            "workflow": sample_quality([r["status"] for r in workflow_rows]),
            "adversarial": sample_quality([r["status"] for r in edge_rows]),
        },
        "retrieval": retrieval_summary,
        "freshness": {
            "status": "TARGETS_ONLY_NOT_LIVE_VERIFIED",
            "policy": "retailiq/domain/semantic.py",
            "note": "Synthetic timestamp checks are in workflow/edge suites, not a live source SLA.",
        },
        "mcp": {
            "status": "NOT_ASSERTED_FROM_THESE_REPORTS",
            "note": "Actual MCP stdio evidence is a separate CI acceptance gate.",
        },
        "limitations": [
            "A source's pass fraction reflects its bounded test scenarios only",
            "Cross-domain question cases are represented in both contributing source groups",
            "Synthetic fixtures cannot establish production freshness or actual business reliability",
            "Live retrieval quality requires a provider-backed report; RAGAS measures answer quality separately",
        ],
    }


def _read(path: Path) -> dict:
    if not path.is_file():
        raise FileNotFoundError(f"Required evidence report not found: {path.name}")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("Evidence report must be a JSON object")
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description="Aggregate measured RetailIQ reliability evidence")
    parser.add_argument("--queries", default="data/query_audit_report.json")
    parser.add_argument("--workflows", default="data/workflow_audit_report.json")
    parser.add_argument("--edges", default="data/edge_scenario_audit.json")
    parser.add_argument("--retrieval", default=None,
                        help="Optional actual provider report; omit rather than fabricate")
    parser.add_argument("--out", default="data/source_reliability_report.json")
    parser.add_argument("--strict", action="store_true",
                        help="Fail if any supplied independent scenario fails")
    args = parser.parse_args()
    report = build_reliability_report(
        _read(Path(args.queries)), _read(Path(args.workflows)),
        _read(Path(args.edges)), _read(Path(args.retrieval)) if args.retrieval else None)
    target = Path(args.out)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                      encoding="utf-8")
    for source, metrics in report["sources"].items():
        print(source, metrics["pass"], "/", metrics["cases"],
              "fixture scenarios; not a live SLA")
    print("Report:", target)
    return int(args.strict and any(
        suite["fail"] or suite["error"] for suite in report["test_suites"].values()))


if __name__ == "__main__":
    raise SystemExit(main())
