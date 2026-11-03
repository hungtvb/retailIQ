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
- Keep **execution evidence, generated reports, screenshots and traces outside the repository**; retain test code, fixtures and CI configurations inside it. Never commit secrets.
- Do not change unrelated files, create a branch/commit/PR, or merge to `main` unless the user authorizes that action.
