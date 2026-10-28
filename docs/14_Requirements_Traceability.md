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
