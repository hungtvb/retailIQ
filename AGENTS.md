# RetailIQ — Coding Agent Guide

## Find context
- `README.md`: quick start.
- `docs/README.md`: documentation index; read only task-relevant pages.
- `docs/ARCHITECTURE.md`: current architecture and module responsibilities.
- `docs/DESIGN.md`: request flows and task-to-source navigation; load only relevant sections.
- `docs/DATA_API.md`: source-of-truth, KPI and API contracts.
- `docs/implementation/`: **just-in-time, reviewed** per-use-case Implementation Detail; do not load unrelated use cases.

## Documentation Rules

1. Read `docs/README.md` to find the canonical document.
2. Update existing docs before creating new ones.
3. Create new docs only when explicitly approved or required by an approved task.
4. Keep docs consistent with code; distinguish planned, implemented, and verified.
5. Never use `docs/archive/` as current implementation guidance.
6. Update affected docs and links in the same PR; avoid duplicate content.

## Working rules
- Before substantial coding, inspect existing code and dependency versions; research the **latest relevant official documentation**, release notes and compatibility guidance. Cite or link key sources in the task/PR. Small self-contained fixes need only proportionate verification.
- **Challenge before executing:** identify unnecessary complexity, contradictions, security risks and simpler/reusable alternatives. Explain meaningful trade-offs **before** implementing; do not blindly accept a request.
- Understand the requirement and acceptance criteria; make the smallest scoped change. Preserve interfaces unless a migration is explicitly justified.
- **Design-first gate for substantial feature work:** locate the reviewed, **merged** use-case Implementation Detail via `docs/README.md` (for example `docs/implementation/UC-01-backorder.md`; unmerged proposals are drafts). Record its path and approved Git commit SHA in the implementation Issue and code PR **before coding**. Do not treat an unmerged design PR or issue discussion as approved architecture. If a business/temporal/trust contract changes, review the design change first; small compatible corrections can accompany the code PR.
- Keep business calculations in `retailiq/domain/`, orchestration in `retailiq/orchestration/`, HTTP in `retailiq/api/`, retrieval in `retailiq/rag/`, and persistence in `retailiq/infrastructure/`. Existing legacy paths are not an instruction to organize new code by course week.
- Validate business facts against trusted data. Do not silently drop SKU, date, location, ranking or access scope. Never equate deterministic/mock tests with live provider behavior.
- Run targeted tests and relevant scenario checks; report actual results and remaining gaps. Do not claim PASS without execution.
- **Synchronize progress after merge or testing:** in the same work session, update the relevant owner/task and UC parent Issues; update `docs/CAPABILITY_LEDGER.md` only when acceptance status changes. Link the PR/commit and actual test evidence/mode; distinguish **design approved**, **implemented/merged**, **verified**, **accepted**, **pending** and **blocked**. A merged PR is not acceptance; close an Issue only when its acceptance criteria are evidenced. Do not wait for a reminder.
- Keep **execution evidence, generated reports, screenshots and traces outside the repository**; retain test code, fixtures and CI configurations inside it. Never commit secrets.
- Do not change unrelated files, create a branch/commit/PR, or merge to `main` unless the user authorizes that action.

## Agentic LLM simulation testing rule (mandatory)

- **For Agentic behavior tests, mock ONLY the model boundary and run the actual full-mode application path:** compiled LangGraph, request/session context, plan validation, existing read-only SQL, real local MCP/RAG where in scope, result verification and API/SSE. Never treat the separate offline assistant path as proof of LLM understanding, planner decisions, follow-up handling or final response quality.
- **ChatGPT-authored model fixtures:** the implementing assistant must inspect the *current* production prompts, schemas and model-call stages and author versioned realistic outputs. Cover correct, incomplete, contradictory, ambiguous, hallucinated-tool/identifier, malformed/exception and prompt-injection responses, including multi-turn Vietnamese/English questions. A fixture is **simulated LLM output**, not evidence that the deployed provider would produce it.
- **Inject at model construction/invocation**, not by stubbing the router, planner, validator, executor, SQL/MCP results, or final HTTP response. The scripted model must reject an unexpected call/schema or a missing fixture; never silently return a successful fallback.
- **Verify the whole turn:** exact goal/entity/period/warehouse/source scope, committed reference IDs, actual registered capability/tool arguments and execution events, independent SQL/source oracles, provenance and answer completeness/faithfulness. A fluent answer, HTTP 200, presence of a keyword/number, or green mock CI alone is insufficient.
- **Separate evidence modes:** report `offline_synthetic` (domain-only), `simulated_llm_full_graph` (mock model + real full runtime), and `provider-backed` (actual configured model). Never invent token usage or claim model accuracy/cost from fixture runs.
- **Keep targeted paid acceptance:** after simulated tests pass, explicitly opt in to real-provider end-to-end scenarios for model comprehension, plan quality, multi-turn behavior and response quality; use budgets and inspect traces/reports. Do not auto-run paid provider requests on ordinary PRs.
- Keep ordinary offline/unit tests for fast deterministic business invariants; do not delete existing regression gates. See `docs/SCENARIO_ACCEPTANCE.md` for the scenario and reporting contract.
