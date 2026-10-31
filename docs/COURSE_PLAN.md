# RetailIQ — Course Roadmap & Planning Reference

This document owns the **original course-week sequence** and planning context. The stable [product requirements](REQUIREMENTS.md) describe required capabilities independently of teaching weeks. Course phases are **milestones**, not source-code modules or present-day delivery deadlines.

## Original four-week sequence

| Course phase | Focus | Required outcomes (see requirements) |
|---|---|---|
| **Week 1 — Domain AI Assistant** | Natural-language sales/inventory, LangGraph/SQL, product RAG, tracing and evaluation | CAP-01–05; show working queries, architecture and actual-mode LangSmith/RAGAS evidence |
| **Week 2 — Reliable Assistant** | Source freshness, semantics, MCP, customer context and advanced retrieval | CAP-06–10; source reliability and retrieval acceptance |
| **Week 3 — Governed Copilot** | HITL, access control, KPI alerts, usage/cost, Langfuse, DeepEval, security and PromptOps | CAP-11–13; demonstrable security/governance controls and reports |
| **Week 4 — Multi-Agent Retail OS** | Five specialist agents, A2A-style coordination, verification and manager-approved order scenario | CAP-14–15; tested end-to-end coordination with human approval |

The course's mandatory topics are retained even where implementation is incomplete or only simulated. For the exact capability gaps and their evidence modes see the [acceptance ledger](29_COURSE_CAPABILITY_ACCEPTANCE_LEDGER.md).

## Original provisional delivery plan (historical)

The initial project schedule was **27 October – 28 November 2026**: Week 1 (27 Oct–2 Nov), Week 2 (3–9 Nov), Week 3 (10–16 Nov), Week 4 (17–23 Nov), with integration/handoff buffer (24–28 Nov).

The team originally estimated five members at roughly 60 minutes per person per day, including learning. **These assumptions have been superseded**: RetailIQ is now also developed as an independent project; quality and verified requirements take priority over an artificial weekly delivery cut-off.

## Planning and ownership

- **Roadmap:** milestone priorities and course coverage; do not derive runtime module names from course weeks.
- **GitHub Issues/PRs:** feature tasks, owners, acceptance criteria, dependencies, review and temporary migration checklists. Avoid a duplicate task-tracking file.
- **Development order:** prioritize business correctness and verified capabilities; postpone optional infrastructure and speculative abstractions.
- **Historical source:** initial [roadmap](archive/2026-10-30/legacy/16_Roadmap_and_Timeline.md) and [risk register](archive/2026-10-30/legacy/15_Risk_Register_and_Document_Governance.md) are retained in the archive.

[Product](PROJECT.md) · [Requirements](REQUIREMENTS.md) · [Capability status](29_COURSE_CAPABILITY_ACCEPTANCE_LEDGER.md)
