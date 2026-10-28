# Week 1 — Test Evidence (current snapshot)

**Updated:** 2026-10-28. This file is an evidence index, not a claim that real provider E2E passed.

| Check | Result | Evidence / caveat |
|---|---|---|
| Current main CI regression | **276 Python passed; 12 Node passed** | [Week 1 run 40721904503](https://github.com/hungtvb/retailIQ/actions/runs/40721904503) on code commit `224fcb79fe3008e1c6462ed2d83e64a4789de5a3` |
| Current main quality CI | **3 mocked graph tests, 5 localhost E2E groups, 400/400 measured calls passed** | [Quality run 40721904431](https://github.com/hungtvb/retailIQ/actions/runs/40721904431) on the same code commit; isolated temporary fixture remained unchanged during requests |
| PR #3 full CI regression | **260 Python passed; 12 Node passed** | [Week 1 CI run 40718699395](https://github.com/hungtvb/retailIQ/actions/runs/40718699395) on PR head `87ee872de957483233991f74523d5c3869356df2`; installed LangGraph and SQLite checkpoint dependencies |
| PR #3 local E2E and benchmark CI | **3 mocked graph tests and 5 localhost E2E groups passed; 400/400 measured calls** | [Quality run 40718698954](https://github.com/hungtvb/retailIQ/actions/runs/40718698954) on the same PR head; synthetic offline fixture, not external provider evidence |
| Current audit environment | **276 Python passed; 12 Node passed** | Python 3.12.14, including newly merged business golden scenarios. The first run had five `ModuleNotFoundError` failures because `langgraph-checkpoint-sqlite` was missing. Installing that package into a temporary test path resolved them; the full suite then passed. |
| Updated quality runner | **5 localhost E2E groups passed; 160/160 measured calls passed** | Local run with `--samples 20 --output` outside the repo; project SQLite and product document checksums were unchanged. This is synthetic offline evidence for the updated runner, not a CI result. |
| HTTP session concurrency and delete lifecycle | **Passed (mocked checkpoint deletion)** | `tests/test_week1_runtime_scope.py`: 409 for overlapping turns/deletion, cleanup before chat removal, 503 on cleanup failure |
| Read-only retry and provider-call timeout | **Passed (mocked provider)** | `tests/test_week1_runtime_scope.py`: transient vs semantic failures, 20-second default configurable bound and one SDK retry |
| GitHub CI compiled LangGraph | **Passed with mocked provider** | Current main runs above; live external provider remains unverified |
| Live full-mode LangGraph + SQL + Chroma | **Not verified** | `python -m scripts.index_products`, `python -m scripts.full_e2e` with real provider configuration |
| RAGAS evaluation scores | **Not verified** | `python -m scripts.eval_ragas` with live judge/model |
| LangSmith nested traces and model cost | **Not verified** | Enable LangSmith with real key, then inspect trace links and usage |

Historical 43/43, 84-pass and 89-pass counts in earlier handoff notes are older snapshots. Each CI result above applies only to its stated commit.

## Week 1 acceptance rules

- Offline success is evidence for local read-only business logic, UI and error handling only.
- Mocked compiled-graph success is **not** live provider E2E proof.
- A provider timeout limits one SDK call, **not** total request execution or true worker cancellation.
- No human approval/write action, long-term customer memory, MCP, cost governance or advanced distributed resilience is implemented in Week 1. See [the project phase boundaries](00_PROJECT_REQUIREMENTS.md).
