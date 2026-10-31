"""Provider-backed Week 2 retrieval evaluation with source-level metrics.

This is NOT a mock: actual Chroma embeddings are invoked for vector/hybrid.
Run only after scripts.index_products and with configured provider credentials:
  python -m scripts.eval_retrieval --confirm-live --strict

No report is written when a provider/query fails. Never call this through
offline CI and never describe the fake-vector unit suite as live retrieval.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import datetime, timezone
import json
from pathlib import Path
import tempfile
import time
from typing import Callable

from retailiq.rag.indexing import vector_search
from retailiq.rag.advanced_retrieval import hybrid_search
from retailiq.core.config import settings

CASES = (
    ("W2-RAG-01", "Tell me the specifications of USB-C GaN Charger 65W",
     "data/product_docs/EL-003.md"),
    ("W2-RAG-02", "Thông số công suất sạc USB-C GaN Charger 65W?",
     "data/product_docs/EL-003.md"),
    ("W2-RAG-03", "Does USB-C Hub 7-in-1 support HDMI and PD passthrough?",
     "data/product_docs/EL-009.md"),
    ("W2-RAG-04", "What is the warranty for AlphaBook Pro 14?",
     "data/product_docs/EL-001.md"),
    ("W2-RAG-05", "Describe the NovaPhone X OLED display",
     "data/product_docs/EL-002.md"),
    ("W2-RAG-06", "What connections does SwiftMouse Wireless support?",
     "data/product_docs/EL-006.md"),
    ("W2-RAG-07", "What resolution does the ViewMax 27 Monitor offer?",
     "data/product_docs/EL-007.md"),
    ("W2-RAG-08", "Maximum rated power of USB-C Cable 100W 2m?",
     "data/product_docs/EL-004.md"),
)


def evaluate_source_retrieval(
    cases: tuple[tuple[str, str, str], ...],
    search: Callable[[str, int], list[dict]],
    *,
    k: int = 3,
) -> dict:
    """Evaluate actual retrieved evidence, not a canned target or LLM answer."""
    if not cases or k < 1:
        raise ValueError("Retrieval evaluation must have cases and k >= 1")
    results = []
    by_source = defaultdict(list)
    for case_id, question, expected_source in cases:
        start = time.perf_counter()
        contexts = search(question, k)
        latency_ms = round((time.perf_counter() - start) * 1000, 3)
        if not isinstance(contexts, list):
            raise TypeError("Retriever result must be a list")
        sources = [c["source"] for c in contexts[:k]]
        rank = next((i for i, source in enumerate(sources, 1)
                     if source == expected_source), None)
        row = {
            "id": case_id, "expected_source": expected_source,
            "retrieved_sources": sources,
            "hit_at_k": rank is not None,
            "reciprocal_rank": round(1 / rank, 6) if rank else 0.0,
            "latency_ms": latency_ms,
        }
        results.append(row)
        by_source[expected_source].append(row)
    def aggregate(items):
        return {
            "questions": len(items),
            "source_recall_at_k": round(sum(x["hit_at_k"] for x in items) / len(items), 4),
            "mrr": round(sum(x["reciprocal_rank"] for x in items) / len(items), 4),
            "mean_latency_ms": round(sum(x["latency_ms"] for x in items) / len(items), 3),
        }
    return {
        "summary": aggregate(results),
        "per_source": {src: aggregate(rows) for src, rows in sorted(by_source.items())},
        "cases": results,
    }


def report_live(*, k: int = 3) -> dict:
    cfg = settings()  # Require real provider settings; do not expose credentials.
    modes = {
        "vector": lambda q, n: vector_search(q, k=n),
        "hybrid": lambda q, n: hybrid_search(q, k=n),
    }
    metrics = {name: evaluate_source_retrieval(CASES, search, k=k)
               for name, search in modes.items()}
    return {
        "evaluation_mode": "live_provider_embeddings_and_chroma",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "model": cfg.embedding_model,
        "top_k": k,
        "dataset": "synthetic_product_docs_heldout_queries_v1",
        "strategies": metrics,
        "limitations": [
            "Source retrieval measures do not establish answer faithfulness",
            "A small synthetic fixed set is not a production retrieval benchmark",
            "Run RAGAS separately on complete generated answers",
        ],
    }


def save_atomic(target: Path, report: dict) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    name = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8",
                                         dir=target.parent, prefix=target.name+".",
                                         suffix=".tmp", delete=False) as handle:
            name = Path(handle.name)
            json.dump(report, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
        name.replace(target)
    finally:
        if name is not None:
            name.unlink(missing_ok=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="Actual provider-backed retrieval quality")
    parser.add_argument("--confirm-live", action="store_true",
                        help="Accept actual embedding API calls")
    parser.add_argument("--strict", action="store_true",
                        help="Exit nonzero when source Recall@3 is below 1.0")
    parser.add_argument("--out", default="data/retrieval_eval_report.json")
    args = parser.parse_args()
    if not args.confirm_live:
        parser.error("Provider-backed evaluation requires --confirm-live")
    report = report_live(k=3)
    target = Path(args.out)
    save_atomic(target, report)
    for strategy, data in report["strategies"].items():
        print(f"{strategy}: recall@3={data['summary']['source_recall_at_k']} "
              f"MRR={data['summary']['mrr']} "
              f"mean_latency_ms={data['summary']['mean_latency_ms']}")
    print("Report:", target)
    return int(args.strict and any(
        value["summary"]["source_recall_at_k"] < 1.0
        for value in report["strategies"].values()
    ))


if __name__ == "__main__":
    raise SystemExit(main())
