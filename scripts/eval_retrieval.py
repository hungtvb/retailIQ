"""Provider-backed Week 2 retrieval evaluation with source-level metrics.

This is NOT a mock: actual Chroma embeddings are invoked for vector/hybrid.
Run only after scripts.index_products and with configured provider credentials:
  python -m scripts.eval_retrieval --confirm-live --strict

No report is written when a provider/query fails. Never call this through
offline CI and never describe the fake-vector unit suite as live retrieval.

The v2 query set is paraphrased so no query repeats the expected document's
heading, mixes product-doc targets with knowledge-doc distractors, and adds
an abstention case that no indexed document answers.
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

DATASET = 'synthetic_product_docs_heldout_queries_v2'

# (case id, question, expected source; None means the retriever must abstain)
CASES: tuple[tuple[str, str, str | None], ...] = (
    ("W2-RAG-01", "How much power can the 65W GaN adapter deliver over a single USB-C port?",
     "data/product_docs/EL-003.md"),
    ("W2-RAG-02", "Sạc GaN 65W hỗ trợ chuẩn sạc nhanh nào?",
     "data/product_docs/EL-003.md"),
    ("W2-RAG-03", "Does the 7-in-1 hub pass HDMI and power through to a monitor?",
     "data/product_docs/EL-009.md"),
    ("W2-RAG-04", "How long is the warranty on the 14-inch AlphaBook laptop?",
     "data/product_docs/EL-001.md"),
    ("W2-RAG-05", "What display panel does the NovaPhone handset use?",
     "data/product_docs/EL-002.md"),
    ("W2-RAG-06", "Which wireless connections does the SwiftMouse support?",
     "data/product_docs/EL-006.md"),
    ("W2-RAG-07", "What resolution and refresh rate does the 27-inch ViewMax panel offer?",
     "data/product_docs/EL-007.md"),
    ("W2-RAG-08", "What is the maximum rated power of the two-metre 100W cable?",
     "data/product_docs/EL-004.md"),
    ("W2-RAG-09", "Which Bluetooth version and noise cancelling does the AirPulse pair have?",
     "data/product_docs/EL-005.md"),
    ("W2-RAG-10", "Is the Orbit keyboard wired, and does it use mechanical switches?",
     "data/product_docs/EL-008.md"),
    ("W2-RAG-11", "What screen size and storage does the NovaTab tablet come with?",
     "data/product_docs/EL-010.md"),
    # Knowledge-doc distractors: real files under data/knowledge/.
    ("W2-RAG-12", "Where are online orders dispatched from when stock is available?",
     "data/knowledge/shipping_policy.txt"),
    ("W2-RAG-13", "Is the demo warranty statement a real manufacturer warranty?",
     "data/knowledge/warranty_faq.html"),
    # Abstention: live warehouse stock is not in the indexed documentation.
    ("W2-RAG-14", "What is our current stock level in the Hanoi warehouse right now?",
     None),
)


def evaluate_source_retrieval(
    cases: tuple[tuple[str, str, str | None], ...],
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
        if expected_source is None:
            # Abstention: correct only when the retriever returns no evidence.
            rank = None
            hit = not sources
            reciprocal_rank = 1.0 if hit else 0.0
        else:
            rank = next((i for i, source in enumerate(sources, 1)
                         if source == expected_source), None)
            hit = rank is not None
            reciprocal_rank = round(1 / rank, 6) if rank else 0.0
        row = {
            "id": case_id, "expected_source": expected_source,
            "abstention": expected_source is None,
            "retrieved_sources": sources,
            "hit_at_k": hit,
            "reciprocal_rank": reciprocal_rank,
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

    def label(source):
        return '<abstention: no expected source>' if source is None else source

    return {
        "summary": aggregate(results),
        "per_source": {label(source): aggregate(rows) for source, rows
                       in sorted(by_source.items(), key=lambda item: label(item[0]))},
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
        "dataset": DATASET,
        "strategies": metrics,
        "limitations": [
            "Source retrieval measures do not establish answer faithfulness",
            "A small synthetic fixed set is not a production retrieval benchmark",
            "Queries are paraphrased so the expected document heading is not in the question",
            "The set mixes product docs with knowledge-doc distractors and one abstention case",
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
