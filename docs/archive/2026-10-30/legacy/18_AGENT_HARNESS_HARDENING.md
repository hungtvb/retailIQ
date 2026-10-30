# Agent Harness / Orchestration — Module Hardening

**Scope:** Week 1 LangGraph router, domain specialists, handoff, checkpoint lifecycle, retriable read paths, and LangChain model-directed replenishment supervisor. The assistant remains read-only. This document distinguishes local/CI graph execution from remote provider E2E.

## Contracts and failure modes

| Component | Contract | Failure handling / test |
|---|---|---|
| Router | Only `stock/revenue/top/product/decision`; business-deterministic routes may not be overridden by a narrow model prediction | Invalid model output or provider exception falls back to deterministic classification and records sanitized `router_fallback`; no arbitrary tools |
| Follow-up resolver | SKU inferred only from **user-authored** explicit product references, or top seller retrieved by reviewed SQL | Do not mine assistant/RAG output for product identifiers; ambiguous references abstain |
| State input | At most last 12 user-authored messages, each capped at 500 characters | Avoid replaying large/untrusted assistant outputs into checkpoints; no cross-session context |
| Graph topology | Command-goto destinations declared on node definitions | No global `__annotations__` mutations or accidental double execution from static edges |
| SQL specialists | Retry *only* transient read-side timeout/connection/busy-locked errors | LangGraph RetryPolicy max two attempts (1 original + 1 retry); no retry for semantic, validation, permission errors |
| Terminal output | Intent must be allowlisted, active agent must match intent, answer nonblank and <=20k chars, records/contexts lists | Raise `GraphResultError` for missing/misrouted/stale/invalid result; never return incomplete answers as verified |
| Sales -> Inventory | Typed LangGraph Command handoff, only for actual stock follow-up from Sales | Verified compiled graph handoff; handoff shape is validated at terminal result |
| Supervisor | Sales evidence **before** inventory, exactly one each; inventory request must use verified top-seller SKU | Reject early inventory, wrong SKU, repeated sales/stock, empty/mismatched evidence; ignore invented model numbers |
| Checkpoint SQLite | Single in-process graph for one configured path | Explicit owned connection, `close_checkpoint_graph()` and atexit cleanup; fail if path changes during process lifetime instead of cross-wiring checkpoints |

## Test evidence

- `tests/test_orchestration_hardening.py`: router invalid/missing output and timeout, user-only bounded history, terminal validation, transient retry, retry exhaustion, permanent error no retry, compiled SqliteSaver state isolation, failed-turn recovery, cached connection cleanup and stable graph annotations.
- `tests/test_supervisor_contract.py`: actual supervisor verification with fake model scheduler; enforce Sales -> Inventory ordering, valid top SKU, one call per specialist, required nonempty evidence and failed delegation behavior.
- Existing `tests/test_langgraph_smoke.py`, `tests/test_harness_fixes.py` and `tests/test_week1_runtime_scope.py` continue covering compiled graph, handoff, checkpoint delete, streaming and read-only retry contracts.
- Run via `RETAILIQ_REQUIRE_LANGGRAPH=true python -m pytest -q -rs` after installing project requirements. Full GitHub CI also runs six Node frontend formatting tests.

## Resource, error and security policy

- The Chat API holds a per-session local mutation lock while a turn runs, so concurrent writes to the same session return busy; independent sessions can run separately.
- A successful turn persists exactly one user and one assistant message. No success is persisted after an exception.
- Session deletion attempts checkpoint removal before deleting chat records and surfaces cleanup failures as 503.
- Normal SQL read retry is bounded by the LangGraph policy. Model provider timeouts are per-call (configured in `retailiq/core/config.py`), **not** a guaranteed whole-graph deadline.
- No arbitrary SQL from the model: specialists invoke only reviewed read-only functions.
- Supervisor ignores LLM-crafted final answer text and derives the replenishment rule exclusively from verified Sales/Inventory evidence.

## Known limitations / not yet accepted

- **No guaranteed end-to-end cancellation:** disconnected SSE clients stop consuming events, but synchronous running LLM/tool calls can complete later. A workflow deadline and cooperative cancellation need separate design.
- **Single-process checkpoint ownership:** the cached SQLite connection and in-memory locks are not distributed. Reconfiguring checkpoint path requires explicit shutdown of the old graph resource. Concurrent shutdown while requests are active is unsupported.
- **Checkpoint growth:** history per turn is bounded but SQLite checkpoint versions accumulate over a long-lived session. Benchmark retention, VACUUM, backup, storage quotas and lifecycle cleanup before a public/multi-tenant deployment.
- **No auth/RBAC:** the local-only Week 1 app is not a public production service.
- **No remote LLM E2E:** tests use actual compiled LangGraph + SqliteSaver with deterministic model/tool substitutes, not paid model traffic or semantic route evaluation.
- **No long-term memory or distributed coordination:** deliberately left to the appropriate later modules.

**Module gate:** CI green + exact failure-mode evidence is necessary, but not sufficient to claim production readiness. Any remote provider/tracing/load claim requires its own measured evidence.
