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

## Architecture review closure & Fiction implementation baseline (2026-11-03)

**Architecture Reviews 01–10: DESIGN APPROVED. Implementation and capability acceptance: OPEN.** Approval records architectural decisions, **not** code completion, live data freshness, provider quality or business E2E PASS. Retain course capability IDs in [Requirements](REQUIREMENTS.md); use [Capability Ledger](29_COURSE_CAPABILITY_ACCEPTANCE_LEDGER.md) only for *evidenced* acceptance, not review approval.

| Architecture review | Approved issue / implementation owner |
|---|---|
| 01 — Chat lifecycle & verified-first SSE | [#21](https://github.com/hungtvb/retailIQ/issues/21) |
| 02 — Hybrid verified conversation context | [#22](https://github.com/hungtvb/retailIQ/issues/22) |
| 03 — Bounded capability planning/orchestration | [#23](https://github.com/hungtvb/retailIQ/issues/23) |
| 04 — Fiction data/tool access contract | [#31](https://github.com/hungtvb/retailIQ/issues/31) |
| 05 — Governed SQL & semantic business definitions | [#31](https://github.com/hungtvb/retailIQ/issues/31) |
| 06 — Inventory/Order MCP reuse of SQL capabilities | [#26](https://github.com/hungtvb/retailIQ/issues/26) |
| 07 — Source-document RAG ingestion & measured retrieval | [#27](https://github.com/hungtvb/retailIQ/issues/27) |
| 08 — Evidence fitness, time and source reliability | [#28](https://github.com/hungtvb/retailIQ/issues/28) |
| 09 — Minimal local authentication, authorization & HITL | [#29](https://github.com/hungtvb/retailIQ/issues/29) |
| 10 — Truthful UI/data-flow graph & Fiction E2E quality | [#30](https://github.com/hungtvb/retailIQ/issues/30) |

**Approved boundaries:**
- Fiction Retail is a coherent **independent synthetic company dataset**. RetailIQ reads one **unified** business SQLite snapshot, source Markdown documents and a matching release manifest; no database/source generation belongs inside its agent runtime. Preserve canonical `product_id`, Fiction SKU, USD, policy `as_of` and source provenance across SQL/MCP/RAG/answers. Historical rebasing does **not** establish live freshness.
- SQL/domain functions own authorized read-only business facts and deterministic rules. Review 08 owns evidence fitness/claim support; the LLM does not certify truth or execute unrestricted SQL. Procurement remains a **separate deferred simulated read-only MCP integration**, roughly 20 inbound PO-line records/two tools; it is not part of #26 or a table already present in Fiction unified.
- Review 07 is architecturally complete but **retrieval/chunking defaults remain evidence-driven evaluation choices**, not unclosed architectural design. Review 10 reuses React/SVG, SSE and existing traces; no default React Flow migration or new observability platform.

**Verified release boundary:** [Fiction Retail unified v1.0.0](https://github.com/hungtvb/fiction-retail/blob/main/manifest.json), repository main `d92aa3fb28b9fb1b492fdc2e784b8cd4d49ebb72`. The separately uploaded SQLite file was checked against release SHA-256 `015b0a84d8d93870c6facd359347f4c039bc7fc570000890c581010d0451af42`; **this does not mean RetailIQ runtime, source documents, Chroma index or CI have been migrated/accepted**. The active RetailIQ `main` baseline remains `cdd37eeb2ff99521901437f72bae186761a592b3` with legacy fixture paths. Do not conflate accepted architectural design with historical/mock provider PASS.

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

### Dependency-first implementation sequence (not deadlines)

| Milestone | Bounded deliverable and acceptance gate | Owner / dependencies |
|---|---|---|
| **M0 — Fiction data & SQL foundation** | Import single unified business DB + manifest, verify hashes/schema/entity/time semantics; reuse compatible code from draft PRs #24/#25; independent SQL/rule oracles for UC-01 backorder, UC-02 refund reconciliation, UC-03 sales→inventory | [#31](https://github.com/hungtvb/retailIQ/issues/31), then [#28](https://github.com/hungtvb/retailIQ/issues/28) |
| **M1 — Trusted business capabilities** | Correct scoped, read-only order/inventory/sales/refund/case and effective policy rules; allow verified partial analysis when evidence is absent | [#31](https://github.com/hungtvb/retailIQ/issues/31), [#28](https://github.com/hungtvb/retailIQ/issues/28) |
| **M2 — Agent intelligence** | Hybrid context and bounded LangGraph orchestration; real local MCP Inventory/Order, Fiction RAG source-doc ingestion/retrieval evaluation | [#22](https://github.com/hungtvb/retailIQ/issues/22), [#23](https://github.com/hungtvb/retailIQ/issues/23), [#26](https://github.com/hungtvb/retailIQ/issues/26), [#27](https://github.com/hungtvb/retailIQ/issues/27) |
| **M3 — Authorized use/HITL** | Two local roles, session ownership, enforced server-side scopes, authenticated one-shot review; no actual order/refund/price/stock mutation | [#29](https://github.com/hungtvb/retailIQ/issues/29); auth baseline can progress alongside M2 |
| **M4 — Integrated UI & SSE** | Verified findings/evidence/limitations, invocation-aware active nodes and directed actual request/result data edges; verified-first SSE | [#30](https://github.com/hungtvb/retailIQ/issues/30), [#21](https://github.com/hungtvb/retailIQ/issues/21) |
| **M5 — E2E acceptance** | Fiction golden scenarios + independent oracle + actual MCP + real LLM/RAG + browser/UI/trace evidence; update capability ledger only with versioned measured results | Existing test harnesses and [#30](https://github.com/hungtvb/retailIQ/issues/30) |

**PR status at planning baseline:** [#24](https://github.com/hungtvb/retailIQ/pull/24) and its stacked [#25](https://github.com/hungtvb/retailIQ/pull/25) are **draft/not merge-approved**; parts of SQL, identity/follow-up and tests can be reused, but source-era 2024 assumptions, generated duplicate RAG narratives and incomplete month coverage must be reconciled with the unified 2026 release. Review in order, do not merge automatically.

**Planning rule:** One approved issue per bounded implementation outcome where useful, reused code before new abstractions, independent scenario tests with negative cases, separate offline/mock/local-MCP/provider modes. No extra roadmap, parallel status spreadsheet, speculative infrastructure, or inferred owner/deadline. Course-specific required RAGAS, LangSmith, Langfuse, DeepEval and multi-agent acceptance remain tracked by the existing [CAP ↔ W-ID ledger](29_COURSE_CAPABILITY_ACCEPTANCE_LEDGER.md), not silently dropped.

**Historical task snapshot (2026-10-31; see live issues for current state):** [Issue #1](https://github.com/hungtvb/retailIQ/issues/1) is closed (historical documentation work); [Issue #6](https://github.com/hungtvb/retailIQ/issues/6) is open for real owner/approval sign-off. No owner, approval date or technical acceptance should be fabricated from the original course timetable. Completed documentation PRs #11–#16 improve the **documentation baseline**, not current product capability acceptance.

**Historical source:** initial [roadmap](archive/2026-10-30/legacy/16_Roadmap_and_Timeline.md) and [risk register](archive/2026-10-30/legacy/15_Risk_Register_and_Document_Governance.md) remain preserved without becoming the active tracker.

[Product](PROJECT.md) · [Requirements](REQUIREMENTS.md) · [Capability status](29_COURSE_CAPABILITY_ACCEPTANCE_LEDGER.md)
