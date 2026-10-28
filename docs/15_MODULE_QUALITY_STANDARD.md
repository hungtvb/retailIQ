# RetailIQ — Module Quality Standard

**Goal:** Strengthen each module to production-engineering quality, rather than accumulate agent features to complete a checklist.

## Definition of done — every module

1. **Contract:** owner, inputs/outputs, domain invariants, error types, dependency boundaries and persistence semantics.
2. **Clean code:** cohesive functions, testable I/O boundaries, no duplicate business logic or hidden side effects.
3. **Reliability:** classify transient versus permanent errors; retry only idempotent operations; explicit timeouts and cancellation semantics; bounded resource usage and guaranteed cleanup.
4. **Security:** validate all input, use least-privilege tools, prevent prompt/secret leakage and unauthorized data exposure.
5. **Testing:** happy path, empty/invalid data, dependency failures, concurrency, retries/timeouts, rollback, resource exhaustion and security edge cases.
6. **Evidence:** test commands, environment, results, failure reproduction and limitations. A mock passing is not a live integration passing.

## Chat & Sessions — first hardened slice

- **Atomic turn:** one successful request writes one user/assistant pair; failure writes neither.
- **Same-session concurrency:** reject overlapping local writes; independent sessions operate concurrently.
- **Memory:** reference-counted session locks disappear after use; session GET returns the latest 200 messages in chronological order and a messages_truncated indicator, without deleting older records in SQLite.
- **Input limits:** enforce 500-character question and maximum 20,000-character persisted assistant answer.
- **Streaming:** maximum 8 active SSE workers; 128 events buffered per stream; fast 503 plus Retry-After on overload; completed worker releases its slot even if response body was never consumed.
- **Disconnect:** stop enqueueing new events after stream close, but do not claim a synchronous model call can be forcibly cancelled.
- **Local security:** reject nonlocal peers/Host headers. This is not authentication and is not a safe public deployment.
- **SQLite lifecycle:** even failure during connection initialization closes the handle; no half-written turns.
- **Regression:** tests/test_chat_module_hardening.py (locks, races, overload, cleanup, host checks, memory bounds, atomic writes, initialization-failure cleanup).

### Remaining risks

- Full-request deadline and cancellation are not guaranteed; SDK timeouts bound individual model calls, not an entire workflow.
- Per-process locking is not a distributed lock; do not claim multi-instance safety.
- Database retains historical rows by design; retention, pagination and per-tenant quotas remain to design.
- **Local smoke result:** 85 PASS / 1 SKIP on a reconstructed project snapshot with Chat/Sessions and SQL adapter hardening applied, including six Chat and five SQL local integration tests. The targeted local run measured **84% branch-aware coverage** across API HTTP + Sessions + SQL adapter (HTTP 77%, Sessions 91%, SQLite adapter 94%). This is diagnostic only, not a verified CI run of the GitHub HEAD or a production reliability certification.
- Real LangGraph + provider E2E, load/soak and production security remain unverified.

## SQL Data Access — second hardened slice

- **Leak prevention:** SQLite connections are explicitly closed on both successful and failing queries; Python's connection context manager alone does not close the handle.
- **Least privilege:** existing reviewed SELECT calls are retained, opened with SQLite mode=ro and PRAGMA query_only; caller-supplied values must use bound parameters.
- **Resource bounds:** return at most 10,000 rows; SQLite busy timeout 3s and progress-handler-based execution deadline 4s for long queries; values are defaults to benchmark with the fixture.
- **Failure handling:** invalid SQL/argument shape rejects immediately; missing or locked database remains a typed SQLite error; no automatic retry here to avoid stacked retries with LangGraph.
- **Tests:** tests/test_sql_adapter_hardening.py covers exact results, parameter binding/injection, denied writes, row limit, timeout, missing table/DB and connection close on success/failure.
- **Local regression on representative reconstructed code:** 85 PASS / 1 SKIP including 6 Chat hardening cases and 5 SQL hardening cases; main branch CI has not been verified.
- **Limitations:** this is a read-only query adapter, not a production SQL firewall; reviewed query ownership stays in Sales/Inventory. Performance benchmarks, SQLite write-load contention and distributed DB access are not yet validated.

## Inventory and Sales — business correctness hardening (current)

- **Inventory:** normalize/validate SKU, check quantity and availability arithmetic, detect duplicate or orphaned locations, verify timezone-aware timestamps; missing stock is lack of evidence, not an invented 0.
- **Sales:** explicit month boundaries (including December rollover), completed-order filtering, accurate integer-VND net revenue, stable tie-breaking, input-line validation and rejected orphan product references.
- **Replenishment:** do not infer a purchase need when top seller has no inventory evidence.
- **Evidence:** [Inventory & Sales Hardening](16_INVENTORY_SALES_HARDENING.md) and `tests/test_inventory_sales_hardening.py`. The historical reconstructed-source run was **123 passed / 1 skipped / 1 deselected**; later [PR #3 Week 1 CI](https://github.com/hungtvb/retailIQ/actions/runs/40718699395) passed 260 Python and 12 Node tests.
- **Deferred:** freshness SLA, returns/refunds and multi-timezone semantic governance, true production auth.

## Product Knowledge / RAG — retrieval, index and grounding hardening

- **Crash consistency:** write an index dirty journal before Chroma changes. On partial upsert/delete, retrieval fails closed until the next indexing run reconciles pending and committed chunk IDs.
- **Provenance:** only return finite-scored matches whose source/chunk IDs are in the committed manifest; never index implicitly during a user query.
- **Prompt safety:** document text is untrusted JSON evidence; validate exact [S1] source references and append provenance paths outside model output. Citations are NOT semantic faithfulness proofs.
- **Resource bounds:** maximum 10 MiB per input document; 1000 files; 1500 chunks per file; 10,000 chunks corpus-wide; ZIP expansion/member limits and PDF page limit. Read locks exclude in-process index writes.
- **Failure behavior:** strict ingestion fails on corrupt documents; incomplete offline lexical extraction does not silently answer. REST and SSE return actionable index_not_ready rather than fabricated product facts.
- **Tests:** [Product RAG Hardening Report](17_PRODUCT_RAG_MODULE_HARDENING.md) and tests/test_rag_module_hardening.py (partial vector writes/deletes, crash recovery, invalid manifest, malicious contexts, provider timeouts, archive bombs and resource limits).
- **Verified CI baseline:** GitHub Actions run 40708549592 — 200 Python tests + 6 Node tests PASS; commits after that run require their own fresh CI verification.
- **Not claimed:** RAGAS semantic correctness, prompt-injection immunity, measured live vector relevance, production multi-process indexing or access control.

## Agent Harness / Orchestration — runtime reliability hardening

- **Router:** invalid/missing structured model classification and provider errors use deterministic fallback; cross-domain business intent is not silently overridden.
- **Context:** bounded user-authored turns only; do not take a SKU from an assistant or untrusted RAG response. Intent and agent must agree at every terminal result.
- **Graph:** explicit destinations without mutating global function annotations; compiled graph regression covers failure recovery and separate checkpoint thread IDs.
- **SQL retry:** at most two attempts for transient locked/busy/timeout on idempotent SQL specialist paths; no retry for domain-data errors.
- **Supervisor:** Sales must run before Inventory, exactly once each; inventory SKU must match verified top seller; no output is accepted from unverified/incomplete delegation.
- **Checkpoint:** managed owned SQLite connection with explicit close and atexit cleanup; fail safely if database path changes during the process instead of reusing wrong state.
- **Tests and residual-risk disclosures:** [Agent Harness Hardening](18_AGENT_HARNESS_HARDENING.md) and `tests/test_orchestration_hardening.py`, `tests/test_supervisor_contract.py`.
- **Not claimed:** distributed checkpoint safety, whole-graph cancellation/deadline, live provider route accuracy or long-term memory.

## Next modules to harden, in dependency order

| Module | Critical contract / failure modes | Tests before acceptance |
|---|---|---|
| Tools/Data Access | Parameterized, read-only, correctly disposed SQL connections | Injection, DB locked/busy, permission denial, concurrent readers |
| Inventory | available = on_hand − reserved, SKU and location correctness | Unknown/ambiguous SKU, negative availability, stale/duplicate records |
| Sales | completed-order scope, discounts and returns policy, stable ranking | Empty period, cancellations, return handling, ties, money precision |
| Product/RAG | relevant indexed documents and traceable grounded claims | Empty/unrelated corpus, malformed index, prompt injection, embedding failure |
| Agent Harness | bounded graph steps and correct context isolation | Wrong route, retry exhaustion, handoff, checkpoint recovery |
| Observability/Evaluation | safe and bounded metadata, authentic E2E traces | Secrets leak, log rotation, corrupted logs, evaluator outage |
| UI/Response Formatting | inert model input, stable JSON/display contract | XSS, malformed markdown, abort/disconnect, large data, accessibility |
| Cost/ROI | no double count and clearly hypothetical inputs | Zero/negative cases, rounding, high volume, no payback |

Implement one vertical module at a time and close it with failure evidence before adding new features or restructuring into services.
