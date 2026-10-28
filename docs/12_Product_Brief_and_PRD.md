# RetailIQ Copilot — Product Brief and Week 1 PRD

> **Version:** 0.1 · **Status:** Draft for PO/team review · **Last updated:** 2026-10-28
> **Accountable role:** Product Owner · **PO approval:** Pending
> **Baseline:** [Project Requirements](00_PROJECT_REQUIREMENTS.md) and the [official Week 1 rubric](00_WEEK1_OFFICIAL_CHECKLIST.md).

## Product brief

RetailIQ Copilot is a local demonstration assistant for an omnichannel electronics retailer. It answers read-only inventory and sales questions from a synthetic SQLite fixture and answers product-detail questions from local product knowledge documents. Week 1 demonstrates the path from natural-language input to a grounded result, while keeping offline simulation distinct from live model, vector-search, evaluation, and tracing evidence.

**Outcome hypothesis:** store and operations staff can find routine inventory, sales, and product facts with fewer manual lookups. This is unvalidated: no user study, time-saving baseline, or production outcome has been measured.

### Users and stakeholders

| Persona / stakeholder | Need | Evidence status |
|---|---|---|
| Store or inventory operator (assumed primary user) | Check a product's available units across locations and understand reservations | Synthetic scenario; not validated with an external operator |
| Retail operations analyst (assumed secondary user) | Review monthly revenue and top sellers using consistent definitions | Synthetic scenario; not validated with an external analyst |
| Product Owner / reviewer | Confirm scope, rubric coverage, evidence, and known gaps | PO sign-off pending |
| Engineering and QA team | Run locally and distinguish offline, mocked, and live results | Runbook provided; clean-machine review pending |

### Goals and non-goals

**Week 1 goals**

- Answer stock, current synthetic-month revenue, top-seller, and product-detail questions.
- Use read-only SQL for numeric inventory/sales facts and source-addressable documents for product facts.
- Provide deterministic offline mode and separate full mode using LangGraph, an OpenAI-compatible model, and Chroma.
- Treat tests, RAGAS evaluation, and LangSmith tracing as distinct evidence gates; never infer a live pass from an offline or mocked run.

**Week 1 non-goals**

- Writing inventory, placing orders, changing prices, or making autonomous purchasing decisions.
- Production deployment, authentication, tenant isolation, row-level security, or production audit logging.
- Using real retailer/customer data, claiming production freshness, or presenting illustrative ROI as measured savings.

## Scope by week

| Milestone | Planned scope | Current status |
|---|---|---|
| Week 1 · 27 Oct–02 Nov | Local Inventory & Sales SQL assistant, Product RAG, LangGraph routing, RAGAS, LangSmith, demo and evidence | Local code/tests and mocked graph evidence exist. Live LLM, Chroma, RAGAS scores, and LangSmith trace remain unverified. |
| Week 2 · 03–09 Nov | Freshness-aware routing, governed KPI layer, Inventory/Order MCP APIs, customer context, advanced retrieval | Planned; not acceptance for Week 1 |
| Week 3 · 10–16 Nov | Human approval, access controls, alerts, Langfuse, DeepEval, cost/security/governance reports | Planned; not acceptance for Week 1 |
| Week 4 · 17–23 Nov | Five specialist agents, A2A-style orchestration, verification loop, decision report, approved order scenario | Planned; not acceptance for Week 1 |
| Integration buffer · 24–28 Nov | Regression, clean-machine setup, demo rehearsal, evidence and handoff | Target dates and owner assignment pending PO/team review |

See the [Four-Week Roadmap and Timeline](16_Roadmap_and_Timeline.md) for milestone outputs, role responsibilities, and dependencies.

## Prioritized user stories and acceptance criteria

### US-01 — Check available stock (P0)

As an inventory operator, I want available units for a known SKU by location and in total so that I can understand stock available to sell.

- Given a seeded SKU, the answer shows each location's `on_hand`, `reserved`, and `available`, where `available = on_hand - reserved`.
- Total available equals the sum of location-level available values.
- An unknown or ambiguous product reference prompts for a more specific name/SKU and does not select an arbitrary product.
- The answer identifies execution mode; offline output is not described as live LangGraph output.

### US-02 — Review revenue and top sellers (P0)

As a retail operations analyst, I want monthly revenue and top sellers so that I can review the synthetic fixture using published KPI definitions.

- Revenue includes completed orders in the month selected by `RETAILIQ_AS_OF`, applies each order-line discount, and reports channel breakdowns.
- Top sellers rank the five products with the most completed-order units in that month; ties are ordered by SKU.
- Answers use VND, identify the month, and do not imply tax, shipping, or returns are included.
- Offline and full-mode evidence are recorded separately.

### US-03 — Find product facts (P0)

As a store operator, I want product-detail answers grounded in product knowledge so that I can answer product questions without treating a document as stock data.

- The answer includes source information returned by retrieval.
- Product documents provide catalog facts, not real-time inventory.
- Offline lexical retrieval is labeled offline; full-mode Chroma retrieval must be demonstrated before full Week 1 acceptance.

### US-04 — Demonstrate the agent workflow (P0)

As a reviewer, I want to see a request route through the relevant agent/tool path so that I can distinguish the harness from a static answer.

- Full mode executes the compiled LangGraph workflow and returns the final answer and execution metadata.
- A mocked graph test is recorded as mocked evidence, not as a live provider check.
- A real full-mode run is required for the live demo gate.

### US-05 — Evaluate answer quality and tracing (P0)

As a PO/reviewer, I want actual RAGAS results and a correlated LangSmith trace so that quality and execution can be reviewed.

- A real RAGAS run produces a dated result artifact and its failed cases are reviewed.
- A real LangSmith run is visible in the configured project and correlated to a demo request.
- If either service cannot be run, its status remains **NOT TESTED** and the Week 1 live gate remains open.

### US-06 — Preserve local chat sessions (P1)

As a demo user, I want to create, switch, and delete local conversations so that follow-up questions can use the selected session context.

- Create/list/get/delete operations work through `/api/sessions`.
- Successful turns are saved once to the selected session; failed execution does not create a completed answer turn.
- Session content is local demo data, not authenticated or encrypted production storage.

### US-07 — Inspect an illustrative cost/ROI estimate (P1)

As a PO, I want editable assumptions and sensitivity cases so that I can discuss a business case transparently.

- Inputs outside published bounds return validation errors.
- The output labels the report illustrative and keeps the all-in VND budget separate from the informational USD token estimate.
- No token usage, provider quote, time saving, or realized ROI is claimed unless separately measured.

## Minimum non-functional requirements

| Area | Requirement for the local demo | Current status / follow-up |
|---|---|---|
| Input handling | `/ask` accepts a question from 3 through 500 characters; malformed requests return validation errors | Enforced by request schema; see API contract |
| Privacy | Keep keys in local `.env`; do not put secrets or personal/customer data in demo questions; log viewer must not expose prompt text, answers, keys, or stack traces | Key/log protections exist; chat messages persist in local SQLite. No production auth/encryption is provided. |
| Network exposure | Bind to `127.0.0.1`; do not publish the unauthenticated API or logs endpoint | Required by runbook; production deployment out of scope |
| Performance | No response-time SLA is approved. Capture local and live latency before making a performance claim. | Measurement pending; no numeric target claimed |
| Accessibility | Main controls should have labels, visible keyboard focus, keyboard operation, and readable contrast | QA review pending; no conformance claim |
| Reliability/evidence | Report deterministic tests, mocked graph tests, and live external checks separately | Traceability matrix is the status source |
| Compatibility | Python 3.11+ and a local browser for the demo | Verify on the actual demo machine |

## Assumptions and constraints

- The fixture has 10 synthetic products, 3 locations, 30 inventory rows, and 120 synthetic orders. `RETAILIQ_AS_OF` defaults to `2026-10-28`.
- There is no live POS, ERP, warehouse, or product-catalog integration in Week 1.
- The shared OpenAI-compatible endpoint/key serves chat and embedding requests in full mode; LangSmith uses its own key.
- The team has five members and approximately 60 minutes per person per day including learning, per the project working agreement.
- One member may cover multiple roles; named owners must be agreed in the issue/PR before approval.

## Approval

| Decision | Owner role | Status |
|---|---|---|
| Confirm scope, priorities, personas, and acceptance criteria | PO | Pending team review |
| Confirm KPI and data definitions | BA / Domain Analyst | Pending team review |
| Confirm architecture and endpoint behavior | Tech Lead / Backend | Pending team review |
| Confirm evidence and test gates | QA | Pending clean setup and live checks |
| Confirm privacy, local-only boundary, and risks | DevOps / Security | Pending review |
