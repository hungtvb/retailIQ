# RetailIQ Copilot — Requirements Traceability and Acceptance Plan

> **Version:** 0.1 · **Status:** Working matrix; live gates remain open · **Last updated:** 2026-10-28
> **Accountable role:** QA · **PO acceptance:** Pending
> Implementation and mocked tests are not live integration evidence.

## Status vocabulary

| Status | Meaning |
|---|---|
| Implemented | Code path exists; not test evidence by itself |
| PASS — local | Deterministic local test/demo ran and passed |
| PASS — mocked | Code path ran with mocked model/provider; not a live integration result |
| NOT TESTED | No real execution/evidence artifact is recorded |
| BLOCKED | A named dependency or decision prevents verification |
| Planned | Future-week work; not a Week 1 pass/fail claim |

**Evidence snapshot:** Code commit `224fcb79fe3008e1c6462ed2d83e64a4789de5a3` passed [Week 1 CI](https://github.com/hungtvb/retailIQ/actions/runs/40721904503) (276 Python, 12 Node) and [mocked graph/localhost quality CI](https://github.com/hungtvb/retailIQ/actions/runs/40721904431) (3 mocked graph tests, 5 E2E groups, 400/400 measured calls). The local audit also passed 276 Python tests after installing the missing SQLite checkpoint package into a temporary path, plus 12 Node tests. Live LLM, Chroma, RAGAS, and LangSmith checks remain unverified. QA records a dated run and artifact link when updating a status.

## Business objective traceability — separate from Week 1 course gates

The updated business hypothesis is **Faster · Easier · Reliable** through natural-language interaction across existing operational tools; **Replenishment Review is one cross-source demonstration**. These UX outcomes are **not replacements** for mandatory LangGraph/RAGAS/LangSmith/agent-pattern requirements or for the original Week 4 five-agent order scenario.

| Business objective | Measured evidence required | Existing support | Status |
|---|---|---|---|
| **Faster — user task completion** | End-to-end time from receiving question through user-checked correct answer; failures, retries and clarifications documented; equivalent manual tool task and agent task | Synthetic 24-trial pilot can collect durations and correct-only medians; no real end-user baseline | **NOT MEASURED**; API p95 is not a business time metric |
| **Easier — interaction effort** | Counts of clicks/filters/tool switches for manual vs RetailIQ on equivalent tasks | Pilot has optional manual_steps only; no standardized interaction taxonomy or true POS/WMS screens | **PARTIAL INSTRUMENT — NOT MEASURED** |
| **Easier — perceived usability** | Post-task 1–5 ease score with anchored scale + feedback | Pilot notes field can hold comments but does **not** collect/scored structured rating | **NOT IMPLEMENTED in current pilot** |
| **Reliable — correctness and completion** | Independently checked task success/correctness, SKU, month, availability, citations and safe abstention | Golden business tests and offline/mocked graph paths | **PASS — local/mocked calculations only**; live provider not verified |
| **Contextual natural language** | Variants and multi-turn references: “the first one”, “that product”, “what about Hanoi?”; ungrounded ambiguity asks clarification | Selected top-seller / SKU follow-up tests exist, full sequence unsupported | **PARTIAL — additional acceptance tests required** |

**Business gates:** no validated Faster/Easier uplift or ROI until real human observations are collected with a suitable instrument. Four volunteers on synthetic data can provide *exploratory*, not generalizable, results. No numerical success target has been approved. See [Business scope](21_INVENTORY_SALES_BUSINESS_SCOPE.md) and [pilot limitations](23_INTERNAL_SYNTHETIC_BUSINESS_PILOT.md).

## Week 1 traceability matrix

| Requirement / story | Acceptance evidence required | Implementation references | Existing test/evidence | Current status | Accountable role / next action |
|---|---|---|---|---|---|
| US-01 stock by SKU/location | Correct `on_hand`, `reserved`, per-location and summed available values; ambiguous SKU asks for clarification | `retailiq/domain/analytics.py`, `retailiq/assistant.py` | `tests/test_week1.py`, `tests/test_web_smoke.py`; `docs/06_Test_Evidence.md` | PASS — local deterministic logic; full provider run NOT TESTED | QA: capture full-mode answer and verify records against fixture |
| US-02 monthly revenue | Completed-order, line-discount formula; month and channel breakdown; exclusions stated | `retailiq/domain/analytics.py` | `tests/test_week1.py`, `tests/test_web_smoke.py` | PASS — local deterministic logic; full provider run NOT TESTED | BA: approve KPI meaning; QA: capture full-mode answer |
| US-02 top sellers | Top five completed-order units; deterministic tie order | `retailiq/domain/analytics.py` | `tests/test_week1.py`, `tests/test_web_smoke.py` | PASS — local deterministic logic; full provider run NOT TESTED | QA: capture full-mode answer and validate ranking |
| US-03 product knowledge | Source-grounded response; no inference of live stock from documents | `retailiq/rag/loaders.py`, `retailiq/rag/indexing.py`, `retailiq/retrieval.py` | `tests/test_rag_formats.py` verifies parsing/chunking, not live Chroma search | PASS — parser/chunking local tests; Chroma + live embedding NOT TESTED | Tech Lead/QA: run full-mode retrieval and record sources |
| US-04 workflow/router | Compiled graph routes to specialist path; mocked result labeled mocked; live run separate | `retailiq/orchestration/week1_graph.py`, `retailiq/graph.py` | `tests/test_langgraph_smoke.py`, `tests/test_mocked_full_graph_e2e.py`; `docs/06_Test_Evidence.md` | PASS — mocked compiled graph on current main CI; live LLM/Chroma NOT TESTED | Tech Lead/QA: run live stock, sales, and product scenarios |
| US-05 RAGAS | Dated real evaluation result, failed cases reviewed, no fabricated scores | `scripts/eval_ragas.py`, `data/demo_cases.json` | No live result recorded; see `docs/06_Test_Evidence.md` | NOT TESTED | QA: run `python -m scripts.eval_ragas` with approved provider and review artifact |
| US-05 LangSmith tracing | Actual remote trace in project, correlated to demo request | `retailiq/core/config.py`, `retailiq/orchestration/week1_graph.py`, `docs/11_Logging_Observability.md` | Configuration/mocks only; no remote trace recorded | NOT TESTED | Tech Lead/QA: enable tracing with local key, capture trace URL/screenshot |
| US-06 sessions and streamed events | CRUD, isolated histories, SSE ordering and error behavior | `retailiq/api/sessions.py`, `retailiq/api/http.py`, `retailiq/infrastructure/sessions.py` | `tests/test_multi_agent_sessions.py`, `tests/test_chat_stream.py` | PASS — local test evidence recorded | QA: repeat against clean local setup |
| US-07 cost/ROI estimate | Input validation, sensitivity behavior, assumptions shown; no measured-savings claim | `retailiq/api/roi.py`, `retailiq/domain/economics.py` | `tests/test_roi_dashboard.py`, `tests/test_cost_roi.py` | PASS — local tests; business outcomes/token costs remain illustrative | PO/BA: confirm assumption labels before presentation |
| NFR input and safe diagnostics | Question/filter validation; no prompt/key/stack trace in log viewer; loopback-only logs | `retailiq/api/http.py`, `retailiq/api/logs.py`, `retailiq/observability.py` | `tests/test_observability.py`, `tests/test_web_smoke.py` | PASS — local tests; app has no authentication | DevOps/Security: review local-only boundary and retention guidance |
| Clean-machine runbook | Fresh setup, seed, mode selection, smoke test, reset, troubleshooting | `docs/03_Week1_Demo_Runbook.md` | No clean-machine execution recorded in this issue | NOT TESTED | QA: follow runbook from fresh venv; record OS, Python, and result |
| Accessibility and latency | Keyboard/contrast review and measured latency record | `docs/12_Product_Brief_and_PRD.md` | No evidence recorded | NOT TESTED | QA: record findings; PO approves any numerical target |

## Week 1 pattern demo coverage — show paths, not labels

| Pattern | Demo path | Evidence limitation |
|---|---|---|
| **Chain** | Product document retrieval → evidence → generation → citation validation | Sequential path exists, but no explicit LCEL RunnableSequence claimed |
| **Agent and Router** | Request routed to Sales/Inventory/Product tool path | Full model/tool execution must be demonstrated; offline rules are not autonomous agent execution |
| **Handoff** | Sales → Inventory on a grounded stock follow-up | Selected references work; arbitrary “first one” not yet proven |
| **Subagent & Custom Workflow** | Supervisor → verified top seller → exact-SKU inventory → rule/evidence verification | Mocked compiled graph demonstrated; verify actual live agentic supervisor separately |
| **Skill** | Approved domain skill loaded and applied in appropriate execution path | Do not count only returned skill name as proof of behavior |

See [FDE/Harness patterns](07_FDE_Harness_and_Patterns.md) and [official rubric](00_WEEK1_OFFICIAL_CHECKLIST.md).

## Live Week 1 acceptance gates

Each gate remains open until QA records run date, environment/mode, result, and artifact path/link. Do not change a live gate to PASS based solely on code inspection, unit tests, a mock, local JSONL logs, or an offline run.

| Gate | Run / evidence | Close condition |
|---|---|---|
| L-01 Provider readiness | `python -m scripts.check_openai --live` from demo environment | One actual chat and one embedding request succeed; no credentials copied into evidence |
| L-02 Full workflow | Set `RETAILIQ_MODE=full`; run `python -m scripts.full_e2e` | Real answers complete; numeric records agree with fixture; product answer includes source |
| L-03 Chroma retrieval | Run `python -m scripts.index_products`, then a full-mode product question | Actual embedding/index/search run succeeds and source is reviewed |
| L-04 RAGAS | `python -m scripts.eval_ragas` | Real result artifact exists; scores and failed cases are disclosed |
| L-05 LangSmith | Real full-mode request with `LANGSMITH_TRACING=true` and separate local key | Remote project shows a real trace correlated to the request |
| L-06 Clean setup | Follow `docs/03_Week1_Demo_Runbook.md` on target demo machine | Setup, seed, app, smoke checks, reset, and teardown recorded without undocumented steps |

## Evidence record template

Copy one row per run into the PR or release evidence:

| Gate / story | Run date + commit | Python / OS | Mode | Command/scenario | Result | Artifact/link | QA owner |
|---|---|---|---|---|---|---|---|
|  |  |  |  |  | NOT TESTED |  |  |

QA maintains the matrix; PO signs off acceptance; BA confirms KPI meaning; Tech Lead confirms implementation/API behavior; DevOps/Security reviews operational/privacy risks. Named people are not recorded because the team roster/assignments have not been supplied.
