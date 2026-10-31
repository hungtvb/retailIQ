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

## Planning and task traceability

**One source of truth per concern — do not maintain a second task spreadsheet, planning migration document or parallel checklist:**

| Concern | Owner | What belongs there |
|---|---|---|
| Product intent and business outcomes | [Product](PROJECT.md) | Why and for whom; benefit is a hypothesis until measured |
| Required capability and its stable ID | [Requirements](REQUIREMENTS.md) | BR / CAP / QUAL definitions and the [CAP ↔ W-ID crosswalk](REQUIREMENTS.md#requirement-to-course-ledger-crosswalk) |
| Relative sequence and dependency | **This roadmap** | Milestone grouping and delivery principle; original weeks are **not deadlines** |
| Work item, owner, dependency and progress | [GitHub Issues](https://github.com/hungtvb/retailIQ/issues) | One scoped issue only when useful for tracked implementation; no invented assignee or completion |
| Change and review | [GitHub Pull Requests](https://github.com/hungtvb/retailIQ/pulls) | What actually changed, linked issue/requirement, review, test/evidence and known limitations |
| Requirement-level acceptance/gaps | [Capability Ledger](29_COURSE_CAPABILITY_ACCEPTANCE_LEDGER.md) | Last evidenced status, scope, mode and remaining proof; no duplicated issue task status |
| Scenario definition and test oracle | [Testing & Scenario Acceptance](27_BEHAVIORAL_ACCEPTANCE_MATRIX.md) | Positive/negative cases, commands and independent correctness checks |

**Trace chain:** `BR/CAP/QUAL ID` → bounded GitHub Issue (when needed) → implementation PR → scenario/evidence (commit + mode + input + expected/observed + artifact) → capability ledger **only when verified**. The ledger's original `W1-*` … `W4-*` IDs are course acceptance labels, not new project task IDs. Do not rename those historical IDs or infer PASS from a merged PR.

### Task sizing (just-in-time)

For an implementation task, use the GitHub Issue body to capture **requirement ID(s), concrete user/business scenario, minimal in/out scope, acceptance cases (including one important failure), evidence mode/command, and dependencies**. Assign an owner only when confirmed. Keep one reviewable outcome per issue; split only if independent verification or dependencies justify it.

A PR should link to the issue if one exists and state actual **changed paths, requirement IDs, test mode and results, expected-versus-observed business evidence, artifact/trace references and unverified gates**. Documentation-only PRs can proceed without a separate issue; verify documentation links and source alignment, not the full application CI by default.

### Delivery order is driven by evidence, not calendar weeks

1. **Reliability of existing retail questions and context** (CAP-01, CAP-04, QUAL-01–04): reproduce recorded failing query cases with an independent SQL oracle before adding another agent.
2. **Current-commit model/retrieval evaluation** (CAP-02, CAP-05, CAP-10): separate live provider/Chroma, RAGAS and trace evidence from mocked/local results.
3. **Governance before sensitive automation** (CAP-11–13): demonstrate genuine authorized approval, isolation and observable security/evaluation gates; synthetic role pickers are not sufficient.
4. **Then actual specialist coordination** (CAP-14–15): validate specialist tool contracts, real control transfer, verification and human approval; a graph illustration is not execution evidence.

These are **priority candidates**, not pre-approved tickets or claims that dependencies are already satisfied. Retain all course-required capabilities in the requirements, including those deferred until their prerequisites are demonstrable.

**Existing task record at review (2026-10-31):** [Issue #1](https://github.com/hungtvb/retailIQ/issues/1) is closed (historical documentation work); [Issue #6](https://github.com/hungtvb/retailIQ/issues/6) is open for real owner/approval sign-off. No owner, approval date or technical acceptance should be fabricated from the original course timetable. Completed documentation PRs #11–#16 improve the **documentation baseline**, not current product capability acceptance.

**Historical source:** initial [roadmap](archive/2026-10-30/legacy/16_Roadmap_and_Timeline.md) and [risk register](archive/2026-10-30/legacy/15_Risk_Register_and_Document_Governance.md) remain preserved without becoming the active tracker.

[Product](PROJECT.md) · [Requirements](REQUIREMENTS.md) · [Capability status](29_COURSE_CAPABILITY_ACCEPTANCE_LEDGER.md)
