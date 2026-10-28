# RetailIQ Copilot — Risk Register and Document Governance

> **Version:** 0.1 · **Status:** Draft for team review · **Last updated:** 2026-10-28
> **Accountable role:** DevOps / Security for operational risks; PO for product acceptance.
> A role is not a named assignee; team members must be assigned in issue/PR before an item is considered owned.

## Risk register

Severity reflects the current local demo context. Status remains open until the next action has evidence.

| ID | Risk / cause | Severity | Impact | Mitigation / next action | Owner role | Status |
|---|---|---|---|---|---|---|
| R-01 | Real LLM, Chroma, RAGAS, and LangSmith checks have not been run | High | Local or mocked success may be mistaken for live Week 1 completion | Keep live gates NOT TESTED; run and attach dated evidence before claiming full acceptance | QA + Tech Lead | Open |
| R-02 | Inventory/orders are synthetic and do not refresh from retailer systems | High | Answers may be mistaken for operational stock/revenue | Label fixture and reference month in demo; do not use for fulfillment decisions | BA + PO | Mitigating; review before each demo |
| R-03 | API and chat sessions have no authentication or tenant isolation | High | Exposed instance/data may be accessible to callers | Bind only to `127.0.0.1`; do not use public tunnels/reverse proxies; production access controls remain future work | DevOps / Security | Open |
| R-04 | Chat questions and answers persist in local SQLite | Medium | Sensitive content can remain on the demo machine | Use synthetic/non-sensitive prompts; delete demo sessions after use; disclose local storage | DevOps / Security | Mitigating |
| R-05 | Revenue excludes returns/refunds, tax, and shipping | Medium | KPI may differ from finance or marketplace reports | Publish formula in data contract; get BA/PO approval before comparing with real KPIs | BA / Domain Analyst | Pending approval |
| R-06 | Natural-language routing or retrieval can choose the wrong path or return irrelevant content | High | Incorrect business guidance or unsupported product claims | Keep SQL read-only; test ambiguous references; show retrieval source; review live failures; no Week 1 write actions | Tech Lead + QA | Open |
| R-07 | Provider availability, deployment names, or pricing may differ from examples | Medium | Full-mode demo may fail or cost may differ | Run provider readiness check on target environment; confirm deployment names and current rates; treat token cost as illustrative | Tech Lead / Backend | Open |
| R-08 | `python -m scripts.seed` removes and regenerates `data/retailiq.sqlite3` | Medium | Custom fixture edits in that file are lost | Warn before seeding, back up custom data, and use synthetic seed only for demo reset | Tech Lead / Backend | Mitigating; runbook documents reset |
| R-09 | Local Chroma index may be stale, incomplete, or built with another embedding namespace | Medium | Product answers may omit or mis-rank source content | Inspect indexing output; re-index changed docs; record embedding model/endpoint without secrets; rebuild only as needed | Tech Lead / Backend | Open |
| R-10 | Named team owners and PO approval are not recorded | Medium | Review/follow-up work may remain unassigned | Assign one person per role or explicitly record role coverage in issue/PR; PO reviews this draft | PO | Open |
| R-11 | No response-time SLA or accessibility review is recorded | Low | Demo usability/performance may be overstated | QA records target-machine latency and keyboard/contrast findings; PO approves any numerical target | QA + PO | Open |

## Role ownership and work outputs

| Role | Accountable outputs for issue #1 | Review/acceptance action |
|---|---|---|
| Product Owner | Product goal, scope/out-of-scope, priority, assumptions, acceptance criteria | Approve `docs/12_Product_Brief_and_PRD.md` and Week 1 acceptance state |
| BA / Domain Analyst | User workflows, glossary, revenue/stock/top-seller definitions, data dictionary | Confirm business terms in `docs/13_Data_and_API_Contract.md` |
| Tech Lead / Backend | Architecture, ERD/schema, endpoint behavior, mode semantics, setup/reset details | Confirm implementation matches architecture, runbook, and API contract |
| QA | Story-to-test/evidence traceability, clean setup, smoke checks, live gate evidence | Maintain `docs/14_Requirements_Traceability.md`; do not pass live gates without run evidence |
| DevOps / Security | Local network boundary, secret handling, data retention, operational risk/actions | Review this register and runbook security limits |

**Named owners:** TBD by the team. The repository has no current member-to-role roster, so no individual assignment is inferred. One member may cover multiple roles if recorded in the issue/PR.

## Document control

| Document | Source-of-truth purpose | Accountable role | Status |
|---|---|---|---|
| `docs/00_PROJECT_REQUIREMENTS.md` | Four-week baseline and course/project scope | PO | Baseline; changes require explicit scope decision |
| `docs/00_WEEK1_OFFICIAL_CHECKLIST.md` | Official Week 1 rubric | PO / QA | Reference; preserve rubric meaning |
| `docs/12_Product_Brief_and_PRD.md` | Product outcome, personas, scope, stories, priority, acceptance | PO | Draft; approval pending |
| `docs/16_Roadmap_and_Timeline.md` | Target dates, phase outputs, milestones, dependencies, role accountability | PO | Draft estimate; team review pending |
| `docs/13_Data_and_API_Contract.md` | Current schema, KPI definitions, and HTTP behavior | Tech Lead / BA | Draft; engineering/domain review pending |
| `docs/14_Requirements_Traceability.md` | Story-to-code/test/evidence map and live gates | QA | Working matrix; clean setup/live gates open |
| `docs/15_Risk_Register_and_Document_Governance.md` | Risk ownership, document owners, review process | DevOps / Security + PO | Draft; named assignments pending |
| `docs/03_Week1_Demo_Runbook.md` | Setup, mode selection, smoke test, reset, teardown, troubleshooting | Tech Lead / DevOps | Draft; clean-machine check pending |
| `docs/06_Test_Evidence.md`, `docs/09_Week1_Checklist_and_Evidence.md` | Dated verification results and rubric status | QA | Evidence record; see each live gate |

## Change and approval rules

1. Keep implementation and contract/document changes in the same PR when an API, data definition, scope, run command, or security boundary changes.
2. Record version/status, last-updated date, accountable role, and approval state near the top of product/contract/status documents.
3. Link requirements to tests and evidence. Record run date and commit for observed results.
4. Use **NOT TESTED** when no real execution artifact exists; use **PASS — mocked** for provider mocks; reserve live PASS for real external integration runs.
5. PO approves priority/scope; BA approves KPI meaning; Tech Lead approves API/architecture accuracy; QA owns evidence status; DevOps/Security owns operational/security review.
6. Issue #1 tracks this documentation package. Leave it open until the team assigns named owners, reviews the draft, and records pending acceptance items.
