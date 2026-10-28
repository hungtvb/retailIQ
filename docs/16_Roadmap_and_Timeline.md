# RetailIQ Copilot — Four-Week Roadmap and Timeline

> **Version:** 0.1 · **Status:** Draft estimate for team planning · **Last updated:** 2026-10-28
> **Target window:** 2026-10-27 through 2026-11-28 · **PO approval:** Pending

This is a provisional calendar plan: four one-week delivery phases followed by a five-day integration, demo, and handoff buffer. Dates are targets, not commitments. The plan assumes five team members with roughly one hour per person per day; confirm working days, named owners, and provider access with the team.

## Timeline and exit outcomes

| Phase | Target dates | Focus and expected outputs | Accountable roles | Exit condition |
|---|---|---|---|---|
| Week 1 — Product and evidence baseline | 27 Oct–02 Nov | Approve PRD and KPI/API contract; stabilize the local demo; run full-mode stock, sales, and product flows; capture RAGAS and LangSmith evidence when credentials are available; record remaining gaps | PO, BA / Domain Analyst, Tech Lead / Backend, QA, DevOps / Security | Week 1 checklist reviewed; each live gate has a dated result or remains explicitly NOT TESTED/BLOCKED |
| Week 2 — Freshness and governed data access | 03–09 Nov | Define freshness tiers and source guarantees; implement the shared KPI semantic layer; expose inventory/order read operations through MCP; add retrieval improvements and source-level reliability notes | BA / Domain Analyst, Tech Lead / Backend, QA | Stock/revenue/top-seller definitions are approved; freshness behavior and MCP operations have reproducible tests/demo evidence |
| Week 3 — Governance and controls | 10–16 Nov | Deliver a vertical slice for manager approval of a sensitive pricing action; define and demonstrate row-level access boundaries; add KPI alert flow, LangFuse/DeepEval evidence, cost review, and security findings | DevOps / Security, Tech Lead / Backend, QA, PO | Approval and access-control scenarios have explicit pass/fail evidence; security risks have actions and owners |
| Week 4 — Multi-agent retail workflow | 17–23 Nov | Implement the five required specialists; define A2A ownership/control transfer; add verification loop and decision report; demonstrate an order scenario that waits for manager approval | Tech Lead / Backend, PO, BA / Domain Analyst, QA | End-to-end scenario shows all required agent handoffs and verification; no sensitive action is finalized without approval |
| Integration and handoff buffer | 24–28 Nov | Stabilize interfaces; run regression and clean-machine setup; rehearse the final demo; update evidence, runbook, risk register, and unresolved items | QA, Tech Lead / Backend, DevOps / Security, PO | PO accepts the documented scope/evidence or records deferred items and their owners; demo package is ready by 28 Nov |

## Milestones

| Date | Milestone | Decision / evidence |
|---|---|---|
| 27 Oct | Kickoff and scope baseline | Confirm named role owners, capacity, and access to required services |
| 02 Nov | Week 1 review | Review local demo, PRD/KPI baseline, and live evidence status |
| 09 Nov | Week 2 review | Review freshness, semantic layer, and MCP inventory/order slice |
| 16 Nov | Week 3 review | Review approval, access-control, evaluation, and security evidence |
| 23 Nov | Week 4 feature review | Review five-agent order scenario and verification loop |
| 28 Nov | Final acceptance and handoff | PO decision, final demo, evidence links, open risks and follow-up owners |

## Dependencies and planning rules

- Assign named people to the PO, BA/Domain Analyst, Tech Lead/Backend, QA, and DevOps/Security roles. A person may cover multiple roles if the team records that assignment.
- Confirm live model, embedding, LangSmith, and evaluation access early in Week 1. If access is unavailable, keep the corresponding gate NOT TESTED/BLOCKED and show a clearly labelled local or mocked path.
- Define KPI and freshness semantics before implementing MCP tools or multi-agent decisions; downstream acceptance depends on those definitions.
- Keep one demoable vertical slice per phase. If capacity is constrained, cut optional depth before weakening security/approval boundaries or claiming unverified evidence.
- The 24–28 Nov buffer is for integration, QA, demo rehearsal, and handoff; it is not an extra feature week.

## Role responsibilities by milestone

| Role | Ongoing responsibility |
|---|---|
| PO | Owns priorities and scope decisions; accepts phase outcomes and final handoff |
| BA / Domain Analyst | Owns workflow, KPI, data-source, and freshness definitions |
| Tech Lead / Backend | Owns architecture, API/MCP contracts, agent implementation, and technical runbook |
| QA | Owns traceability, acceptance evidence, regression, and clean-machine verification |
| DevOps / Security | Owns operational boundaries, access/security review, secret handling, and risk actions |

See [Project Requirements](00_PROJECT_REQUIREMENTS.md) for the four-week capability baseline and [PRD](12_Product_Brief_and_PRD.md) for product stories and acceptance criteria.
