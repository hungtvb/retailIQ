# Engineering Baseline — Documentation and Source Improvement Plan

**Status:** proposed migration, not completed work. This document lives under planning; product design and source architecture are not organized by course week.

## Goals and constraints

- One canonical document for each important concern; a minimal root README and AGENTS.md.
- Keep existing behavior and course-required capabilities while removing week-based naming **from permanent architecture and code organization**.
- Keep executable tests, reusable fixtures and CI definitions in Git; store generated evidence and reports externally.
- Preserve history and backward compatibility where needed. Changes must be staged in small reviewed PRs.
- Build an engineering wiki progressively to explain technical choices, alternatives, trade-offs and practical learning; do not pre-generate an encyclopedia.
- Prefer a modular monolith and incremental cleanup over a framework rewrite.

## Initial inventory and migration matrix

The following is a **proposal**, not a deletion authorization.

| Current location | Proposed action | Intended ownership |
|---|---|---|
| `README.md` | Keep short | Product introduction + quick start + docs link |
| `AGENTS.md` | Keep short | Agent navigation + nonnegotiable engineering rules |
| `docs/PROJECT.md`, `docs/RETAILIQ_HIGH_LEVEL_OVERVIEW.md` | Compare, consolidate later | Product/business |
| `docs/COURSE_PLAN.md` | Split course chronology from stable requirements later | Requirements + planning roadmap |
| `docs/ARCHITECTURE.md` | Review against code; remove week framing later | Current architecture |
| `docs/DATA_API.md` | Retain unless duplication found | Data and API contracts |
| `docs/26_FOUR_WEEK_GRAPH_WORKFLOWS.md`, `docs/28_PRODUCT_WORKSPACE_V1.md` | Extract reusable design notes; archive historical detail | Feature design |
| `docs/27_BEHAVIORAL_ACCEPTANCE_MATRIX.md`, `docs/29_COURSE_CAPABILITY_ACCEPTANCE_LEDGER.md` | Separate acceptance definitions, roadmap status and historical results | Requirements + quality + planning |
| `docs/weeks/week-01/` and `docs/archive/` | Classify and preserve unique content; migrate generated evidence only after external backup | Archive / external evidence |
| `retailiq/orchestration/week1_graph.py`, `retailiq/domain/workflow_demo.py` | Audit imports and responsibilities; refactor only if justified by behavior and tests | Orchestration |
| `web/` and `frontend/` | Define primary UI and migration contract before deletion | Frontend |

## Delivery sequence

1. **Foundation (this PR):** concise README/AGENTS and documentation navigation; no runtime or evidence moves.
2. **Documentation consolidation:** establish canonical product, requirements, architecture, design and development guides; move week labels to a capability-based roadmap.
3. **Evidence extraction:** select external storage; preserve/check original files, run identifiers and links before changing the repository; do not confuse Git deletion with history erasure.
4. **Planning and wiki:** roadmap, GitHub Issues for tasks, small learning articles and ADRs only for meaningful decisions.
5. **Source audit and incremental refactoring:** module responsibilities, legacy adapters, UI ownership, names and compatibility; verify with targeted/scenario/full checks.

## Acceptance for each migration PR

- Scope, changed paths, link updates and migration rationale are clear.
- No important requirement or historical source is lost.
- Documentation cross-references resolve; relevant code and scenario tests run if behavior changes.
- No generated execution evidence is added to the repository.
- No unsupported PASS, live-provider, security or business-ROI claims are introduced.

## External evidence boundary

An external evidence record should identify a requirement/scenario, commit SHA, execution mode, run time, actual outcome and artifact location. **Do not build an evidence platform** or import historical reports into this planning document. A test definition is not a test result.
