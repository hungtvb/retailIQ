# RetailIQ — Coding Agent Guide

## Find context
- `README.md`: quick start.
- `docs/README.md`: documentation index; read only task-relevant pages.
- `docs/ARCHITECTURE.md`: current architecture and module responsibilities.
- `docs/DATA_API.md`: source-of-truth, KPI and API contracts.
- `docs/planning/ENGINEERING_BASELINE.md`: staged documentation/code cleanup plan.

## Working rules
- Before substantial coding, inspect existing code and dependency versions; research the **latest relevant official documentation**, release notes and compatibility guidance. Cite or link key sources in the task/PR. Small self-contained fixes need only proportionate verification.
- **Challenge before executing:** identify unnecessary complexity, contradictions, security risks and simpler/reusable alternatives. Explain meaningful trade-offs **before** implementing; do not blindly accept a request.
- Understand the requirement and acceptance criteria; make the smallest scoped change. Preserve interfaces unless a migration is explicitly justified.
- Keep business calculations in `retailiq/domain/`, orchestration in `retailiq/orchestration/`, HTTP in `retailiq/api/`, retrieval in `retailiq/rag/`, and persistence in `retailiq/infrastructure/`. Existing legacy paths are not an instruction to organize new code by course week.
- Validate business facts against trusted data. Do not silently drop SKU, date, location, ranking or access scope. Never equate deterministic/mock tests with live provider behavior.
- Run targeted tests and relevant scenario checks; report actual results and remaining gaps. Do not claim PASS without execution.
- Keep **execution evidence, generated reports, screenshots and traces outside the repository**; retain test code, fixtures and CI configurations inside it. Never commit secrets.
- Do not change unrelated files, create a branch/commit/PR, or merge to `main` unless the user authorizes that action.
