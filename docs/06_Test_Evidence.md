# Week 1 — Test Evidence (current snapshot)

**Updated:** 2026-10-28. This file is an evidence index, not a claim that real provider E2E passed.

| Check | Result | Evidence / caveat |
|---|---|---|
| Local deterministic unit/API regression | **89 passed, 1 skipped** | Run `python -m pytest -q -rs`; skip is compiled LangGraph tests because package unavailable in the local execution environment |
| HTTP session concurrency and delete lifecycle | **Passed (mocked checkpoint deletion)** | `tests/test_week1_runtime_scope.py`: 409 for overlapping turns/deletion, cleanup before chat removal, 503 on cleanup failure |
| Read-only retry and provider-call timeout | **Passed (mocked provider)** | `tests/test_week1_runtime_scope.py`: transient vs semantic failures, 20-second default configurable bound and one SDK retry |
| GitHub CI compiled LangGraph | **Not verified in this document** | CI installs LangGraph and requires tests to run without skip; inspect actual workflow results |
| Live full-mode LangGraph + SQL + Chroma | **Not verified** | `python -m scripts.index_products`, `python -m scripts.full_e2e` with real provider configuration |
| RAGAS evaluation scores | **Not verified** | `python -m scripts.eval_ragas` with live judge/model |
| LangSmith nested traces and model cost | **Not verified** | Enable LangSmith with real key, then inspect trace links and usage |

Historical 43/43 and 84-pass counts in earlier handoff notes were **older regression snapshots**, not the current test count.

## Week 1 acceptance rules

- Offline success is evidence for local read-only business logic, UI and error handling only.
- One skipped compiled-graph test is **not** LangGraph E2E proof.
- A provider timeout limits one SDK call, **not** total request execution or true worker cancellation.
- No human approval/write action, long-term customer memory, MCP, cost governance or advanced distributed resilience is implemented in Week 1. See [the project phase boundaries](00_PROJECT_REQUIREMENTS.md).
