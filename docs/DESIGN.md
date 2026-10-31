# RetailIQ — Basic Design & Detail Design

**Status:** implementation-aligned design baseline, reviewed 2026-10-31. Describes current local behavior and important gaps; **not** certification of provider-backed reliability, security or production readiness. This is one focused design note rather than separate speculative BD/DD document sets.

[Product](PROJECT.md) · [Requirements](REQUIREMENTS.md) · [Architecture](ARCHITECTURE.md) · [Data and API contracts](DATA_API.md) · [Capability status](29_COURSE_CAPABILITY_ACCEPTANCE_LEDGER.md)

## Basic Design — boundaries and responsibilities

**User job:** ask retail inventory/sales/product questions, follow up within a session, and inspect sources or workflow evidence. Human review remains required for any sensitive business decision.

| Boundary | Implemented source | Responsibility / trust boundary |
|---|---|---|
| User interface | `web/`, `frontend/` | Chat and execution graph **presentation**; graph visuals do not execute agents |
| HTTP API | `retailiq/api/` | Request validation, chat/session and local workflow endpoints; not an enterprise identity boundary |
| Assistant selection | `retailiq/assistant.py` | Explicit offline deterministic vs full-mode execution |
| Chat orchestration | `retailiq/orchestration/week1_graph.py` | LangGraph router, domain specialists, handoff, optional scoped supervisor and checkpointer |
| Domain decisions | `retailiq/domain/analytics.py`, `retailiq/queries.py`, `retailiq/domain/semantic.py` | Reviewed business definitions and read-only SQL; LLM does **not** write unrestricted SQL |
| Product knowledge | `retailiq/retrieval.py`, `retailiq/rag/` | Offline lexical search or full-mode hybrid/vector retrieval, sourced generation and grounding |
| Data and sessions | `retailiq/infrastructure/` | Synthetic SQLite facts, local session/history, opt-in scoped preference memory |
| MCP | `retailiq/mcp_server.py`, `retailiq/mcp_adapter.py` | Local stdio inventory/order operations; not an external retail API |
| Workflow graph | `retailiq/domain/workflow_demo.py`, `retailiq/api/workflows.py` | Deterministic scenario execution, recorded steps and simulated manager review; **separate from LangGraph chat execution** |
| Observability/evaluation | `retailiq/observability.py`, `scripts/`, optional provider tracing | Distinguish local events, tests, simulated graphs and real model traces |

### Two execution surfaces (do not conflate)

~~~mermaid
flowchart TD
    U[Retail operator] --> UI[Chat / Workspace UI]
    UI --> C[Assistant HTTP endpoints]
    UI --> W[Workflow endpoints]
    C --> M{RETAILIQ_MODE}
    M -->|offline| D[Deterministic lookup]
    M -->|full| G[LangGraph router and specialists]
    D --> S[Reviewed SQL / offline lexical]
    G --> S
    G --> R[Product RAG / LLM where needed]
    W --> F[Deterministic workflow_demo]
    F --> A[Local review record - simulated role]
    S --> E[Evidence and validated answer]
    R --> E
    E --> UI
    F --> V[Recorded events -> graph view]
    V --> UI
~~~

**Execution truth:** the Workspace graph reflects events returned by workflow APIs. A displayed specialist node or control-transfer edge in `workflow_demo.py` is not proof of an independently invoked agent. Actual LangGraph/subagent actions must be evidenced separately.

### Change locality — coding-agent navigation

Read `AGENTS.md` and the [documentation index](README.md) first. Start at the **entrypoint for the requested behavior**, follow its imports, and load only the relevant contract and tests. This table is a source-navigation aid, not a new architectural layer or a claim of test success.

| Task | Inspect first, then follow dependencies | Focused verification |
|---|---|---|
| Incorrect stock/revenue/rank or scoped follow-up | `retailiq/queries.py`, `domain/revenue_plan.py` → `domain/analytics.py` → `infrastructure/sqlite.py` | `python -m scripts.audit_queries --mode offline --strict`; compare exact SKU/period/channel with independent SQL oracle |
| Chat routing, agent handoff, streaming errors | `api/http.py` → `assistant.py` → `orchestration/week1_graph.py` and `orchestration/agents.py` | Relevant `pytest` scenario, then scripted query and SSE/browser acceptance for the affected path; report mode |
| Product document parsing, RAG or citations | `retrieval.py` → `rag/indexing.py`, `rag/advanced_retrieval.py`, document loaders | Parser/index tests; `scripts/eval_retrieval.py` is a separate quality exercise, not automatic live-provider PASS |
| Inventory freshness and local MCP | `api/workflows.py` → `domain/freshness_routing.py`, `mcp_adapter.py`, `mcp_server.py` | `python -m scripts.audit_freshness --strict`; local stdio: `python -m scripts.smoke_mcp_stdio` |
| Workflow graph and simulated approval | `api/workflows.py` → `domain/workflow_demo.py` | `python -m scripts.audit_workflows --strict`; do **not** confuse scenario events with actual LangGraph/A2A execution |
| Workspace/chat graph display | `frontend/src/main.tsx`, `frontend/src/graph.ts`; **legacy** `web/assets/app.js` belongs to `/`, not `/workspace` | `npm --prefix frontend run build` and applicable Chromium smoke; graph displays observed events only |
| Session history, consent and traces | `api/sessions.py` → `infrastructure/sessions.py`, `domain/customer_memory.py` | `python -m pytest -q tests/test_customer_memory.py` plus relevant HTTP/session negative case |

**Compatibility boundaries:** `retailiq/analytics.py` re-exports `domain.analytics`; `retailiq/api/__init__.py` preserves the `uvicorn retailiq.api:app` entrypoint. Keep these paths unless callers/tests are explicitly migrated. `orchestration/week1_graph.py` is an existing source filename, **not** a cue to create new `weekN_*` packages. The two frontend implementations and the deterministic workflow simulator are **intentional independent surfaces**; don't merge or rewrite them simply to reduce the file count. Large source files alone are not a reason to add frameworks or abstractions.

## Detail Design — request and decision flows

### DD-01 — Structured retail question (CAP-01, CAP-04, CAP-07)

**Entry:** chat request (documented `POST /ask` / streaming counterpart) with question and optional session/history.

1. `assistant.ask()` selects offline execution unless `RETAILIQ_MODE=full`; offline answers must identify deterministic mode.
2. Full mode invokes `orchestration/week1_graph.py`: route intent and bounded user-authored follow-up context to Sales, Inventory, Product, Supervisor or general chat.
3. Sales and Inventory specialists use `orchestration/agents.py` and reviewed `queries.do()`/`domain.analytics` functions; the selected metric, SKU, period and location must not be silently changed.
4. Graph returns structured answer, records, sources/contexts, active agent and relevant handoff/subagent metadata; UI renders these without treating metadata as verification.
5. Unresolvable/ambiguous product, missing facts, invalid stock or mismatched business scope must result in a qualified response or error, never a fabricated numeric answer.

**Specific guardrails:** `inventory.available = on_hand - reserved`; revenue uses completed orders and line discounts; top-seller ranking uses completed-order units. Consult `DATA_API.md` for the exact business contract. Follow-up handling is bounded and **not** certified for arbitrary natural-language references.

### DD-02 — Product document question (CAP-02, CAP-05, CAP-10)

- In offline mode, `retrieval.lexical()` searches parsed local document chunks, **not** embeddings or vector DB.
- In full mode, `retrieval.retrieve()` uses `RETAILIQ_RAG_RETRIEVAL=hybrid` (default) or `vector`; ingestion/indexing and embeddings are in `retailiq/rag/`.
- `agents.product_analysis()` builds untrusted-source evidence; the LLM may answer only from this evidence and must supply checked source labels. Invalid/missing citations fail closed.
- Catalog fields such as current price and structured inventory come from reviewed source data, **not** arbitrary document chunks.
- Provider-backed RAGAS/trace results require an actual current-commit run. Parser tests, mocked embeddings and offline lexical search are not equivalent acceptance.

### DD-03 — Cross-source replenishment review (CAP-03, CAP-04)

- Router selects `retail_supervisor` for explicit replenishment decisions; not every stock + sales question should trigger a purchasing recommendation.
- `agents.replenish_review()` defaults to a model-directed supervisor (`RETAILIQ_SUPERVISOR_MODE=agentic`); `deterministic` mode builds two scoped LangGraph SQL subagents.
- Sales identifies ranked SKU from completed orders. Inventory is requested **for that same SKU**; `review_from_evidence()` rejects missing/mismatched SKU or inconsistent availability.
- Current priority rule compares available units against units sold; it is a **screening heuristic**, not demand forecasting or an automatic purchase order.
- To claim a model-directed run, collect its actual invocation/trace. The deterministic path proves only its own execution and business checks.

### DD-04 — Freshness, MCP and the graph workspace (CAP-06–08, CAP-11, CAP-14–15)

- `POST /api/workflows/freshness/route` validates metric and requested freshness tier. Inventory optionally executes an actual local stdio MCP re-read when `RETAILIQ_WORKFLOW_USE_MCP=1`; mismatched SQL/MCP values fail.
- Other synthetic sources lack trustworthy refresh timestamps; a routing decision is **UNVERIFIED** freshness, not live data. Multi-source `/freshness/question` can return `REQUIRES_ORCHESTRATION` without executing tools.
- `POST /api/workflows/run` uses `domain/workflow_demo.py` for labeled synthetic scenarios. `GET /api/workflows/runs/{run_id}` returns the stored run and recorded steps.
- `POST /api/workflows/runs/{run_id}/review` accepts a caller-supplied analyst/manager role to simulate approve/reject. **There is no authenticated manager identity**, real row-level authorization or production order/price mutation.
- Do not describe the five displayed Week 4 roles as five independent autonomous agents or interoperable A2A until actual interfaces and handoff execution are demonstrated.

### DD-05 — Session, failure and evidence boundaries (CAP-04, CAP-09, QUAL-02–07)

- Chat sessions and optional consented preferences are local and scoped. A session UUID is **not** authenticated customer identity; revocation and deletion are required boundaries.
- Retry only transient failures on safe idempotent reads; do not retry sensitive mutations or disguise a provider failure as a factual answer. Keep model context bounded.
- Logs, graph events and screenshots show what was recorded, **not** automatically that a business answer is correct. Preserve source/freshness IDs and exact execution mode.
- Keep secrets and generated traces/reports out of Git. Source tests/fixtures and definitions remain version-controlled.

## Acceptance mapping — representative negative and positive cases

| Design slice | Required scenario / failure | Evidence mode and source |
|---|---|---|
| Structured answer | Stock, revenue, ranking; missing/mismatched SKU, time or location; independently verified totals | Local SQL + business scenario oracle; `docs/27_BEHAVIORAL_ACCEPTANCE_MATRIX.md` |
| Conversation | Same product/period across follow-up; no session leakage; ambiguous reference clarified | Session + graph scenarios; no claim of full open-ended dialogue reliability |
| Product RAG | Correct citations; empty/invalid source; stale index; injected document instructions | Index/grounding tests, then separately **provider-backed** retrieval and RAGAS |
| Multi-source supervisor | Sales-ranked SKU equals inventory SKU; no guessed numbers or purchase write | Scoped graph/subagent events plus negative-case oracle |
| Freshness/MCP | Expired/unknown refresh time; real stdio transport; SQL/MCP disagreement | Local routing/MCP audits; live retailer freshness still pending |
| HITL and multi-agent | Rejection, unauthorized actor, replay/resume, actual transfer and safe finalization | Current local scenario is **simulation only**; authenticated approval gate remains open |

**Evidence contract:** report commit SHA, execution mode, exact command/input, independent expected result, observed output and any remaining gap. Consult the [capability acceptance ledger](29_COURSE_CAPABILITY_ACCEPTANCE_LEDGER.md) for status; a requirement appearing above does **not** mean it passed.

## Design constraints and change policy

1. **Reuse existing paths:** do not create a parallel agent runtime, repository layout, task engine or new abstraction just to match this document.
2. **Smallest truthful design:** diagrams and descriptions must match actual execution, with simulated and provider-backed paths labeled independently.
3. **One source of truth:** Product/Requirements own goals; this Design owns flow boundaries; `DATA_API.md` owns metrics/contracts; the capability ledger owns acceptance status.
4. **Future change:** update the relevant flow and acceptance scenario with the code change, not an unrelated pile of documents. Record substantial architectural trade-offs as short wiki/decision notes when needed.
