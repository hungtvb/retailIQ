"""Week 2 advanced product retrieval: verified hybrid, rewriting and reranking.

Vector search uses the committed Chroma index. Lexical candidates are accepted
only when their current source hash and chunk IDs match the SAME index manifest.
This cannot claim live embedding quality without a provider-backed evaluation.
"""
from __future__ import annotations

import math
import os
import re

from . import indexing

_STOP = frozenset({
    "a", "an", "the", "is", "are", "of", "on", "in", "to", "for", "me", "tell",
    "about", "what", "which", "does", "do", "have", "has", "and", "please",
    "là", "có", "gì", "cho", "tôi", "về", "của", "như", "nào", "những", "được",
})


def _terms(text: str) -> set[str]:
    return set(re.findall(r"[\w-]+", text.casefold(), flags=re.UNICODE)) - _STOP


def rewrite_product_query(question: str) -> str:
    """Deterministic Vietnamese-to-English term expansion, NOT an LLM rewrite.

    Preserve original identifiers, constraints and wording: only append
    bounded equivalents of specific retail document terms.
    """
    if not isinstance(question, str) or not 3 <= len(question.strip()) <= 500:
        raise ValueError("RAG question must be 3–500 characters")
    text = question.strip()
    dictionary = (
        ("bảo hành", "warranty"), ("công suất", "power watts"),
        ("tương thích", "compatibility"), ("thông số", "specifications"),
        ("thời lượng pin", "battery life"), ("sạc", "charger"),
        ("cáp", "cable"), ("kết nối", "connection"),
    )
    expanded = [english for vietnamese, english in dictionary
                if vietnamese in text.casefold() and english not in text.casefold()]
    candidate = text + (" " + " ".join(expanded) if expanded else "")
    return candidate if len(candidate) <= 500 else text


def _indexed_chunks() -> list[dict]:
    """Return only chunks backed by the committed Chroma manifest.

    Never blend updated, deleted, corrupt or not-yet-indexed documents into
    a trustworthy-looking vector response.
    """
    if not indexing._INDEX_SYNC_LOCK.acquire(blocking=False):
        raise indexing.IndexNotReadyError("Product index is being updated")
    try:
        _, manifest_path = indexing._vector_store()
        if indexing._recovery_path(manifest_path).exists():
            raise indexing.IndexNotReadyError("Product index requires recovery")
        if not manifest_path.is_file():
            raise indexing.IndexNotReadyError("Product index missing; run scripts/index_products.py")
        manifest = indexing._read_manifest(manifest_path)
        files = {p.relative_to(indexing.ROOT).as_posix(): p for p in indexing.input_paths()}
        if set(files) != set(manifest):
            raise indexing.IndexNotReadyError("Product sources changed; re-index required")
        for source, path in files.items():
            if indexing._document_sha256(path) != manifest[source]["sha256"]:
                raise indexing.IndexNotReadyError("Product source has changed; re-index required")
        chunks, errors = indexing.plan_chunks()
        if errors:
            raise indexing.IndexNotReadyError("Product ingestion incomplete")
        candidates = []
        for source, values in chunks.items():
            expected = set(manifest[source]["ids"])
            if {item["id"] for item in values} != expected:
                raise indexing.IndexNotReadyError("Product chunk manifest mismatch")
            for item in values:
                candidates.append({"source": source, "text": item["text"][:2400],
                                   "metadata": item["metadata"]})
        return candidates
    finally:
        indexing._INDEX_SYNC_LOCK.release()


def fuse_and_rerank(question: str, vector: list[dict],
                    corpus: list[dict], k: int = 3) -> list[dict]:
    """Use reciprocal-rank fusion, then lexical evidence matching.

    Returns only indexed source-addressable chunks. Scores here are ranking
    signals, not calibrated embedding probabilities or RAGAS quality metrics.
    """
    if not isinstance(k, int) or isinstance(k, bool) or not 1 <= k <= 10:
        raise ValueError("RAG k must be 1–10")
    q = _terms(rewrite_product_query(question))
    if not q:
        return []
    indexed = {c["metadata"]["source_id"]: c for c in corpus}
    lexical = []
    for item in corpus:
        score = len(q & _terms(item["text"]))
        if score:
            lexical.append((score, item))
    lexical.sort(key=lambda x: (-x[0], x[1]["source"], x[1]["metadata"]["source_id"]))

    weights = {}
    methods = {}
    def add(chunk_id: str, rank: int, method: str):
        weights[chunk_id] = weights.get(chunk_id, 0.0) + 1 / (60 + rank)
        methods.setdefault(chunk_id, set()).add(method)

    for i, result in enumerate(vector, 1):
        md = result.get("metadata") or {}
        chunk_id = md.get("source_id")
        if (chunk_id in indexed and
                indexed[chunk_id]["source"] == result.get("source")):
            add(chunk_id, i, "vector")
    for i, (_, item) in enumerate(lexical[:20], 1):
        add(item["metadata"]["source_id"], i, "lexical")

    results = []
    for chunk_id, rrf in weights.items():
        entry = indexed[chunk_id]
        coverage = len(q & _terms(entry["text"])) / len(q)
        # RRF selects sources; bounded content overlap reorders finalists.
        score = (rrf * 30) + (coverage * 0.5)
        if not math.isfinite(score):
            continue
        results.append((score, entry, sorted(methods[chunk_id])))
    results.sort(key=lambda v: (-v[0], v[1]["source"], v[1]["metadata"]["source_id"]))
    return [{**entry, "retrieval_methods": methods,
             "ranking_score": round(score, 5),
             "rewrite_strategy": "deterministic_term_expansion"}
            for score, entry, methods in results[:k]]


def hybrid_search(question: str, k: int = 3) -> list[dict]:
    """Provider vector candidates + manifest-verified lexical candidates."""
    rewritten = rewrite_product_query(question)
    # Keep vector threshold and provenance validation from the existing path.
    vector = indexing.vector_search(rewritten, k=10)
    corpus = _indexed_chunks()
    return fuse_and_rerank(question, vector, corpus, k=k)
