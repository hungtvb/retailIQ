# Product Knowledge / RAG — Module Hardening

**Scope:** Week 1 read-only product-document RAG with Chroma. No new customer memory, MCP, hybrid retrieval, or write-side behavior. Source-backed answer quality remains an explicit external-evaluation gate.

## Module contract

| Boundary | Guarantees | Failure behavior |
|---|---|---|
| Document discovery/loading | Supported local files only; path must remain under project root; symlink rejected | Reject invalid paths; non-strict extraction reports sanitized errors |
| Multi-format ingestion | MD/TXT/HTML/JSON/CSV/XLSX/DOCX/PDF; max file 10 MiB | Reject malformed/oversized/corrupt input |
| Archive/PDF parsing | ZIP member budget 12 MiB, expanded ZIP total 40 MiB, max 1000 members; PDF max 200 pages | Fail before decompressing or scanning excessively large documents |
| Chunking | Stable chunk IDs and source metadata; at most 1500 chunks per file | Reject excessive chunk output during splitting and before any index mutation |
| Index sync | SHA-256 content tracking, incremental updates, manifest; durable dirty journal before Chroma writes | Fail closed on incomplete upsert/delete; next sync reconciles old + pending IDs |
| Retrieval | Explicit index required; block while writer runs/dirty journal exists; finite relevance [0,1] and valid source/chunk membership | Reject malformed scores and spoofed/unknown document chunks; empty indexed corpus returns empty |
| Grounded generation | At most 3 chunks, 2400 chars each; untrusted evidence serialized as JSON in user message; require exact `[S1]` citations to known chunks | Missing/unknown citations or oversized answer abstains; failed providers propagate |
| Provider | Existing per-call timeout and max 1 retry in the model/embedding client | Do not stack blind RAG retries; provider errors reach API's generic execution failure path |

## Recovery scenario

1. Run `RETAILIQ_MODE=full python -m scripts.index_products` after configuring the model/embedding provider.
2. The indexer computes desired source/chunk IDs and writes a `index_manifest.json.dirty.json` journal **before** changing Chroma vectors.
3. If embedding, upsert or delete fails after partial mutation, the journal remains; **vector_search refuses to serve data**. Both REST and SSE return a safe, actionable `index_not_ready` status/message without exposing internal exception details.
4. Re-run the same indexing command. It deletes the known affected IDs and re-embeds the desired current documents before atomically committing the manifest; on success the dirty journal is removed.
5. If the recovery journal itself is corrupt, the indexer refuses to guess or silently erase it. Operators must investigate and perform a controlled rebuild.

This is **single-process local crash recovery**, not an ACID transaction across Chroma + filesystem and not a distributed indexing lock. A machine crash in the filesystem rename/fsync window and cross-process concurrent indexing need separate reliability validation.

## Citation and trust semantics

- Source chunks are untrusted data, never system instructions; file content cannot invoke tools or change business policies.
- The model is told to cite known IDs `[S1]`, `[S2]`, etc. All emitted IDs must match the evidence passed to that request; provenance paths are attached by backend code, not model-selected paths.
- Merely including a source ID **does not prove semantic entailment**. Claims can still be unsupported or source content malicious; LLM prompt injection resistance and factual faithfulness require live adversarial/evaluation tests.
- Product docs must never be used to infer current stock or revenue. Those facts come from SQL modules.
- The relevance threshold (default 0.40) is an **uncalibrated starting point**, not a measured confidence guarantee.

## Tests and acceptance

`tests/test_rag_module_hardening.py` uses stateful fake Chroma plus a fake chat model to verify: fresh/same-hash/update/remove sync, embedding failure after partial write, deletion failure, recovery, corrupt manifest/journal, empty corpus, score NaN/inf, spoofed chunk IDs, invalid query/k/threshold, writer-reader contention, malformed/oversized documents, ZIP bombs, PDF page caps, strict citation IDs, missing sources, malicious prompt content, provider errors and failure-safe abstention.

The existing `tests/test_rag_formats.py` checks supported document formats and source metadata, and `tests/test_openai_config.py` checks gateway configuration with no network calls.

**Verified GitHub CI after recovery/error-injection tests:** [Run 40708549592](https://github.com/hungtvb/retailIQ/actions/runs/40708549592) — **200 Python tests passed and six Node frontend tests passed**. Newer changes (including global corpus limits and typed API errors) must be checked against their own CI run before acceptance.

## Remaining gaps

- No retrieval relevance calibration on a real labeled dataset; no measured RAGAS faithfulness/answer relevancy or LangSmith provider traces yet.
- No externally enforced document access authorization/RBAC; the demo is localhost-only.
- No data-freshness SLA/hybrid search/reranking or automatic index rebuild on file changes; reindex explicitly after document modifications.
- Offline lexical mode now rejects incomplete document extraction rather than quietly answering from a partial corpus.
- No distributed or multi-process indexing guard. The in-process writer/read lock is not a production index coordination mechanism.
- Chroma persistence/manifest can still require operator-managed backup/rebuild and disk-quota/soak testing at scale.

**Next quality gate:** run current HEAD GitHub Actions end-to-end with required LangGraph dependencies, then separately test real Chroma embeddings and LLM with explicit remote provider credentials.
