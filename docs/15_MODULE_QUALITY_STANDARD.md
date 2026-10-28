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
- **Input limits:** enforce 500-character question and maximum 100,000-character persisted assistant answer.
- **Streaming:** maximum 8 active SSE workers; 128 events buffered per stream; fast 503 plus Retry-After on overload; completed worker releases its slot even if response body was never consumed.
- **Disconnect:** stop enqueueing new events after stream close, but do not claim a synchronous model call can be forcibly cancelled.
- **Local security:** reject nonlocal peers/Host headers. This is not authentication and is not a safe public deployment.
- **Regression:** tests/test_chat_module_hardening.py (locks, races, overload, cleanup, host checks, memory bounds, atomic writes).

### Remaining risks

- Full-request deadline and cancellation are not guaranteed; SDK timeouts bound individual model calls, not an entire workflow.
- Per-process locking is not a distributed lock; do not claim multi-instance safety.
- Database retains historical rows by design; retention, pagination and per-tenant quotas remain to design.
- Real LangGraph + provider E2E, load/soak and production security remain unverified.

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