# Week 1 Code Hardening — Implementation and Acceptance

**Date:** 2026-10-28. Based on the course references at [Lesson 02–05](00_WEEK1_LESSON_REFERENCES.md) and the [compliance audit](13_WEEK1_LESSON_COMPLIANCE_AUDIT.md).

## Implemented changes

| ID | Change | Evidence / caveat |
|---|---|---|
| P0-01 | CI fails if LangGraph package is missing; no silent skip in CI | `.github/workflows/ci.yml`, `tests/test_langgraph_smoke.py` |
| P0-02 | Strict live-mode E2E script (five questions); explicit Chroma indexing before requests | `scripts/full_e2e.py`, `scripts/index_products.py`. **Not run with real provider** |
| P0-03 | LangGraph metadata correlates safe `request_id`/`session_id`; session-based `thread_id` | `orchestration/week1_graph.py`, `observability.py`. **Real remote LangSmith trace unverified** |
| P0-04 | Relevance filtering (no automatic top-k claims), source-citation gate, verified SQL evidence | `rag/indexing.py`, `agents.py`, `tests/test_harness_fixes.py`. Score threshold requires calibration |
| P0-05 | RAGAS script retained; separate live acceptance and evaluation | `scripts/eval_ragas.py`. **No real RAGAS score yet** |
| P1-01 | Full-mode model-directed Supervisor using LangChain `create_agent`; SQL subagent tools with scoped evidence | `orchestration/agentic_supervisor.py`. Unit tests use fake model; live provider unverified |
| P1-02 | Supervisor skill participates in model prompt; Sales/Inventory skill content returned on-demand by their tools | `retailiq/skills/`, `agentic_supervisor.py`. Read-only SQL nodes no longer falsely imply prompt-driven skills |
| P1-03 | Session-backed LangGraph `SqliteSaver` checkpointer and unique-SKU recognition | `week1_graph.py`, `assistant.py`. Runtime persistence unverified in this offline environment |
| P1-04 | Optional native graph `updates` stream bridged into existing redacted SSE event pipeline | `RETAILIQ_NATIVE_GRAPH_EVENTS=true`, `week1_graph.py`. Native runtime not yet live-verified |
| P1-05 | Existing Product Agent token usage retained; **full Router/embedding cost accounting remains open** | Need real LangSmith usage/pricing before acceptance |
| P2-01 | Removed Chroma `sync_index()` from each question; one cached session graph/checkpointer per process | `rag/indexing.py`, `week1_graph.py` |
| P2-02 | Bounded SSE queue terminal-event writes; bounded agent recursion | `api/http.py`, `agentic_supervisor.py`. Connection cancellation/auth/cost budgets remain production work |

## Local test evidence

Offline source regression: **89 passed, 1 skipped** at implementation time. Skip = compiled LangGraph test unavailable because package couldn't be installed in the local tool environment. This does **not** prove real LLM, Chroma, or LangSmith execution.

## Real full-mode acceptance runbook

```bash
pip install -r requirements-full.txt
cp .env.example .env
# Configure OPENAI_BASE_URL, OPENAI_API_KEY, CHAT_MODEL, EMBEDDING_MODEL.
# Set RETAILIQ_MODE=full and optionally LANGSMITH_TRACING=true + API key.
python -m scripts.seed
python -m scripts.index_products
python -m pytest -q -rs
python -m scripts.full_e2e
python -m scripts.eval_ragas
```

Review a real trace in the LangSmith project separately. The E2E report intentionally leaves `langsmith_remote_trace_verified=false` and `ragas_scores_verified=false`; those must not be silently marked PASS.

## Minimal Week 1 runtime safeguards (2026-10-28)

- Same-session request overlap: local `session_mutation` guard returns 409 on synchronous requests, or a `session_busy` event on SSE; no multi-process locking claims.
- Session deletion: logically delete LangGraph checkpoints first via `SqliteSaver.delete_thread`; preserve the chat session if checkpoint cleanup fails.
- Read-only SQL nodes: up to 2 attempts only for transient read failures (network/timeout/SQLite busy); invalid SKUs and permission failures are not retried.
- Chat/embedding provider call: `RETAILIQ_PROVIDER_TIMEOUT_SECONDS=20` by default (range 1–120), with one SDK retry; no total request deadline or cancellation.
- Five additional tests in `tests/test_week1_runtime_scope.py`; current local regression 89 PASS / 1 SKIP.

**Deferred by lesson/project phase:** advanced retries/timeouts/long-term memory/MCP (Week 2); human approval, RBAC and advanced cost governance (Week 3); autonomous order/pricing/fulfilment writes (Week 4). These should not block Week 1's read-only demo.

## Critical limits

- A source citation string is not factual entailment. Calibrate vector relevance and evaluate hallucination/negative queries against a golden dataset.
- `SqliteSaver` is for one local process, **not** multi-worker production. No tenant authentication or production permission controls.
- LangSmith may capture full model prompts and outputs; local JSONL purposefully does not.
- `create_agent` and mocked delegation tests do not prove real model tool selection or provider compatibility.
- ROI remains illustrative; per-call measured cost, retries, and financial governance still need implementation.
- Native node event streaming is optional until independently tested with installed LangGraph.
