# RetailIQ Documentation

Use this index to load **only the documentation needed for the task**.

| Need | Canonical source |
|---|---|
| Problem, target users and expected product value | [Product](PROJECT.md) |
| Required business and technical capabilities | [Requirements](REQUIREMENTS.md) |
| Course milestones and original planning sequence | [Roadmap / Course Plan](COURSE_PLAN.md) |
| System design and implementation boundaries | [Architecture](ARCHITECTURE.md) |
| Request paths, component behavior and detailed execution boundaries | [Basic & Detail Design](DESIGN.md) |
| Implementation Detail for an approved vertical slice | [UC-01 Backorder Investigation](implementation/UC-01-backorder.md) (use its reviewed/merged revision) (others added only when scheduled) |
| KPI definitions and current HTTP/MCP contracts | [Data & API](DATA_API.md) |
| Verified Fiction SQL release and local setup | [Fiction Runtime](FICTION_RUNTIME.md) |
| Testing approach, scenarios and reproducible commands | [Testing & Scenario Acceptance](SCENARIO_ACCEPTANCE.md) |
| Capability-level acceptance status and missing evidence | [Capability Ledger](CAPABILITY_LEDGER.md) |
| Engineering rationale, alternatives, trade-offs and learning references | [Engineering Wiki](wiki/README.md) |

## Documentation quality

Write for the reader and the task: state the **purpose, scope/current status, authoritative references and verifiable acceptance**. Keep headings short and avoid repeating other canonical documents. Distinguish **proposed**, **approved/planned**, **implemented**, **verified** and **historical** claims. Use a small Mermaid flowchart when it clarifies architecture or execution; for UC details, prefer goal → flow → components → contracts/errors → acceptance. This is guidance, not a heavyweight template.

## Reference material

- [Dated Week 1 execution evidence](archive/2026-11-03/week-01/EVIDENCE.md) — historical results only; do not treat as current-commit acceptance
- [Dated project assessment](archive/2026-10-31/RETAILIQ_HIGH_LEVEL_OVERVIEW.md) — historical snapshot; Product, Design and Acceptance now have canonical owners
- [Older notes and records](archive/README.md)

The original course-week structure belongs to the [roadmap](COURSE_PLAN.md), not the permanent product or source architecture. Do **not** load archived documents by default for implementation; use them on demand for provenance only. Some legacy module filenames remain until their behavior is explicitly migrated.

**Governance:** The six mandatory create/update rules live in [AGENTS.md](../AGENTS.md); this index maps canonical owners. **Documentation lifecycle:** Review/merge design in `docs/` **before feature code**; link its path + approved commit SHA from the implementation issue and code PR. Issues track work; PRs track changes/review; generated test evidence stays outside Git. See [Design-first change policy](DESIGN.md#design-first-change-policy). A draft use-case detail is **not approved implementation**.

**Evidence policy:** test definitions and CI configuration remain in Git. Generated results, traces, screenshots and benchmark reports belong outside the repository; preserve already committed historical evidence before removal.

[Quick start](../README.md) · [Coding agent guide](../AGENTS.md).
