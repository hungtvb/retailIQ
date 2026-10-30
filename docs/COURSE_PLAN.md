# RetailIQ Copilot — Project Requirements (Weeks 1–4)

> **Source and status:** This document organizes the four-week project brief supplied by the team in the conversation. It is the **requirements baseline**, not a statement that every feature has been built. Where the original wording was not quoted verbatim, the scope is faithfully summarized; verify against the course handout if its wording differs.
>
> **Domain:** #15 Retail / E-commerce  
> **Project title:** RetailIQ Copilot — Omnichannel Inventory Intelligence & Conversational Analytics  
> **Working scenario:** An omnichannel electronics/accessories retailer, with synthetic inventory, products, sales and order data for a local demonstration.

## Business objective

Enable retail operators to ask natural-language questions about inventory, sales, product details, customer context and orders, progressing from a domain AI assistant to a governed, multi-agent Retail OS. Numerical facts must be grounded in authoritative transactional data; document answers must be grounded in retrieved sources. Do not confuse a deterministic offline simulation with live agent or RAG evidence.

## Week 1 — Designing and Developing a Domain AI Chat Assistant

**Scope:** Inventory & Sales Assistant with Natural Language Query.

### Required technical concepts and components

- **LangGraph + SQL Tool + Product RAG:** A workflow routes natural-language questions to reliable inventory/sales SQL or product documentation retrieval.
- **LangChain + Vector Database:** Product documents are ingested, chunked and retrieved using vector search with embeddings.
- **RAGAS Evaluation:** Evaluate product-document answers using a documented question set and actual evaluation metrics.
- **LangSmith Tracing:** Observe model, workflow and tool execution; capture real traces for the demo.

### Demonstration questions

1. How many units of Product A are currently in stock?
2. What is revenue this month?
3. Which products are top sellers?
4. What are the features/details of a particular product?

### Evidence expected

A working local demonstration, architecture and workflow diagrams, factual/sourced answers, trace evidence, evaluation results, testing and limitations. The separate **Week 1 presentation checklist** is at [00_WEEK1_OFFICIAL_CHECKLIST.md](weeks/week-01/README.md); implementation evidence is at [09_Week1_Checklist_and_Evidence.md](weeks/week-01/EVIDENCE.md).

## Week 2 — Scalable and Reliable Domain AI Chat Assistant

- **Freshness-aware routing:** Choose among real-time, 15-minute, hourly and daily freshness expectations according to the query and source.
- **Governed semantic layer:** Centralized and consistent definitions for measures such as stock, revenue, top sellers and order state.
- **MCP Inventory APIs and MCP Order APIs:** Expose domain operations/resources via MCP and integrate them through a LangChain MCP adapter.
- **Customer context memory:** Support short-term conversational memory and an appropriate long-term memory strategy.
- **Advanced retrieval:** Hybrid retrieval, reranking and query rewriting.
- **Deliverable:** Reliability and accuracy reporting by data source, with clear limitations and freshness guarantees.

## Week 3 — Governed Retail Copilot

- **Human-in-the-loop approvals** for sensitive actions such as pricing changes.
- **Row-level security** and governed access to operational data.
- **KPI alerts** and controlled business-monitoring flows.
- **Token optimization** and practical cost measurement/dashboarding.
- **Langfuse tracing** and agent observability.
- **DeepEval regression evaluation**, including repeatable quality checks.
- **Security review:** Observation/reporting, vulnerability identification, mitigation and remediation tracking.
- **PromptOps and governance reporting.**
- **Deliverable:** Governance and security reports plus demonstrated controls and evaluation evidence.

## Week 4 — Autonomous Omnichannel Retail OS

Build and orchestrate five required specialist agents:

1. **Inventory Search Agent**
2. **Fulfilment Optimisation Agent**
3. **Customer Context Agent**
4. **Dynamic Pricing Agent**
5. **Order Management Agent**

### Required coordination and end-to-end flow

- **A2A-style agent architecture** with explicit ownership, communication and control transfer.
- **Multi-agent orchestration** and a **verification loop**.
- **Deep agent report generation** for decisions and operational justification.
- **Full order scenario** demonstrating multi-agent coordination, with **human manager approval** before the sensitive action is finalized.

## Delivery boundaries by week (avoid implementing future scope early)

| Week | In scope | Intentionally deferred |
|---|---|---|
| **Week 1** | Read-only Sales/Inventory SQL, Product RAG, LangGraph Router/Specialists/Supervisor, scoped context and SQLite chat sessions/checkpoints, basic provider timeout/read retries, SSE + LangSmith tracing evidence, RAGAS, illustrative Cost/ROI, tests and demo | No approval flow, no live order mutations, no long-term customer memory, no MCP integrations |
| **Week 2** | Data freshness, semantic layer, MCP inventory/order integration, customer memory, hybrid retrieval, measurable reliability; strengthen retries/timeouts based on measured failures | No price/order write approval yet |
| **Week 3** | Human-in-the-loop approval, security/RBAC, cost limits/alerts, tracing/evaluation governance | No autonomous order fulfilment yet |
| **Week 4** | Five domain agents and cross-agent execution for fulfilment/pricing/order workflows, with manager approval for sensitive writes | No unapproved autonomous business mutations |

**Scope rule:** A pattern may be demonstrated read-only in Week 1 without implementing its later operational business feature. Never label future-week requirements as Week 1 acceptance blockers unless the Week 1 rubric explicitly requires them. All Week 1 execution remains local and synthetic.

## Team delivery constraints (working agreement; not course rubric)

- Team size: **5 people**.
- Working capacity: approximately **60 minutes per person per day total**, including learning and implementation.
- **Local demonstration every week**; cloud deployment is not required for weekly demos.
- Synthetic data and mock integrations are permitted for development, but must be labeled and must not be represented as live production data.
- Keep secrets local: never commit `.env`, keys, customer credentials or private raw traces.

## Scope boundaries and progress

- **Requirements** above describe what the project must eventually address, not the current completion state.
- The Week 1 source may include Router/Subagent/Handoff/Skill/session/logging improvements from iterative FDE work; these are implementation decisions and **do not replace** the Week 1 required LangGraph + SQL + Product RAG + RAGAS + LangSmith evidence.
- Weeks 2–4 functionality must not be reported as complete merely because a related pattern was demonstrated in Week 1.
- Status/evidence belong in [09_Week1_Checklist_and_Evidence.md](weeks/week-01/EVIDENCE.md), not here.

## Traceability

- [Four-week roadmap and target timeline (2026-10-27 to 2026-11-28)](COURSE_PLAN.md)
- [Product brief and prioritized Week 1 stories](PROJECT.md)
- [Data dictionary, KPI and API contract](DATA_API.md)
- [Requirements-to-code/test/evidence matrix and live acceptance gates](weeks/week-01/EVIDENCE.md)
- [Risk register, roles and document governance](COURSE_PLAN.md)
- [Week 1 official presentation and demo checklist](weeks/week-01/README.md)
- [Week 1 evidence matrix and acceptance gates](weeks/week-01/EVIDENCE.md)
- [FDE / Harness Architecture / Agent Patterns](weeks/week-01/DESIGN.md)
- [FDE Multi-Agent and Chat Sessions](weeks/week-01/DESIGN.md)
- [Cost and ROI assumptions](weeks/week-01/DESIGN.md)

## Working timeline and responsibilities

The dates below come from the provisional 2026-10-28 roadmap. They are planning targets, **not fixed delivery commitments**.

| Phase | Target dates | Focus and expected outputs | Accountable roles | Exit condition |
|---|---|---|---|---|
| Week 1 — Product and evidence baseline | 27 Oct–02 Nov | Align Faster/Easier/Reliable business problem and user tasks; demo Router, Subagent, Handoff, Skill, Chain and Custom Workflow alongside real-mode stock, sales and product flows; capture RAGAS and LangSmith evidence when credentials are available; record gaps | PO, BA / Domain Analyst, Tech Lead / Backend, QA, DevOps / Security | Week 1 checklist reviewed; each live gate has a dated result or remains explicitly NOT TESTED/BLOCKED |
| Week 2 — Freshness and governed data access | 03–09 Nov | Define freshness tiers and source guarantees; implement the shared KPI semantic layer; expose inventory/order read operations through MCP; add retrieval improvements and source-level reliability notes | BA / Domain Analyst, Tech Lead / Backend, QA | Stock/revenue/top-seller definitions are approved; freshness behavior and MCP operations have reproducible tests/demo evidence |
| Week 3 — Governance and controls | 10–16 Nov | Deliver a vertical slice for manager approval of a sensitive pricing action; define and demonstrate row-level access boundaries; add KPI alert flow, LangFuse/DeepEval evidence, cost review, and security findings | DevOps / Security, Tech Lead / Backend, QA, PO | Approval and access-control scenarios have explicit pass/fail evidence; security risks have actions and owners |
| Week 4 — Multi-agent retail workflow | 17–23 Nov | Implement the five required specialists; define A2A ownership/control transfer; add verification loop and decision report; demonstrate an order scenario that waits for manager approval | Tech Lead / Backend, PO, BA / Domain Analyst, QA | End-to-end scenario shows all required agent handoffs and verification; no sensitive action is finalized without approval |
| Integration and handoff buffer | 24–28 Nov | Stabilize interfaces; run regression and clean-machine setup; rehearse the final demo; update evidence, runbook, risk register, and unresolved items | QA, Tech Lead / Backend, DevOps / Security, PO | PO accepts the documented scope/evidence or records deferred items and their owners; demo package is ready by 28 Nov |

## Role responsibilities

| Role | Ongoing responsibility |
|---|---|
| PO | Owns priorities and scope decisions; accepts phase outcomes and final handoff |
| BA / Domain Analyst | Owns workflow, KPI, data-source, and freshness definitions |
| Tech Lead / Backend | Owns architecture, API/MCP contracts, agent implementation, and technical runbook |
| QA | Owns traceability, acceptance evidence, regression, and clean-machine verification |
| DevOps / Security | Owns operational boundaries, access/security review, secret handling, and risk actions |

**Authority:** the required four-week course capabilities remain the requirements baseline; implementations and pass/fail evidence are recorded for each week, never inferred from this plan. The original [roadmap](archive/2026-10-30/legacy/16_Roadmap_and_Timeline.md) and [risk register](archive/2026-10-30/legacy/15_Risk_Register_and_Document_Governance.md) are retained as historical snapshots.
