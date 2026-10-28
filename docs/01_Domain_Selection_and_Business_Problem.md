# Domain Selection & Business Problem — RetailIQ Copilot

> Working business hypothesis, confirmed as the project's direction by the sponsor on 2026-10-28; **not validated with real retailer users**. Domain and original four-week course rubric remain unchanged.

## Domain and users

- **Domain:** #15 Retail/E-commerce; B2C Electronics & Accessories; synthetic omnichannel retailer with online sales, two stores and one warehouse.
- **Primary users:** Store/retail operations analysts and staff who need to retrieve and interpret sales, stock and product information. Inventory managers retain business decisions.
- **Not the selected primary problem:** Order Status & Delivery Exception Resolution. Order management and fulfilment still appear in the original Week 2/4 **course requirements** and must not be silently dropped.

## Business problem — interaction complexity, not missing data or tools

Staff may already have POS, OMS, ERP/WMS, PIM, reports and BI dashboards. To answer one business question, they often need to navigate several screens or tools, set filters and date ranges, match SKUs and locations, combine results and interpret KPI definitions.

**Business problem statement:** *Retail business users face complex, multi-step interactions across operational tools and data sources when retrieving, combining and analyzing retail information. These workflows may require unnecessary effort and time, especially for users unfamiliar with the underlying tools or data structures.*

This is a **hypothesis** about a plausible workflow, **not** a claim that all retailers perform manual spreadsheet calculations or that real users have been observed. “Manual” means **human-driven navigation, filtering, joining and interpretation in one or several existing tools**; it does not mean there are no tools. Some retailers already automate stock alerts and replenishment.

## Desired outcomes: Faster · Easier · Reliable

1. **Faster (P0):** reduce end-to-end time from receiving a question to a **correct, checked** answer or decision-support result. Faster is an objective, **not a guaranteed benefit** or measured achievement.
2. **Easier (P0):** reduce navigation/filtering/tool switches and lower the learning burden with a natural-language interface.
3. **Reliable (P0):** maintain correct KPI arithmetic, SKU/period identity, source evidence, limitations and safe abstention; speed without correctness is not success.
4. **Accessible (supporting):** enable users who do not know SQL, report schemas or many application interfaces to complete the same tasks.

**Proposed solution:** RetailIQ Copilot — a conversational natural-language interface that routes requests to vetted read-only sales/inventory tools and source-grounded product retrieval, supports appropriate conversational context and verifies business outputs. Do not imply free-form LLM-generated SQL or automatic purchasing.

## As-is / to-be (hypothesis, not observed field study)

| As-is: human using existing software | To-be: RetailIQ Copilot |
|---|---|
| Open Sales/POS/BI screens and select the reporting period | Ask a business question in natural language |
| Filter completed orders and locate matching products | Reviewed Sales Tool returns the governed metric |
| Navigate Inventory/WMS/ERP or another BI view; reconcile SKU/location | Inventory Tool fetches the *same verified SKU* and location data |
| Calculate/combine/interpret information; consult product docs if needed | Orchestrated tool calls and RAG return an understandable, traceable answer |
| User checks result and manager approves any sensitive decision | **Unchanged:** user verifies important output; manager owns action/approval |

**Do not assume that natural-language processing is always faster.** Tool/model latency, clarification and verification can offset reduced UI effort.

## Focused Week 1 scenarios (all remain in course scope)

1. Available stock for a known SKU by location.
2. Revenue this month, using completed-order net sales.
3. Top-selling products by completed units sold.
4. Product specifications with explicit source evidence.
5. **Cross-source illustration:** top-selling SKU versus available stock → human **Replenishment Review**. This is a demonstrator of multi-tool orchestration, **not the definition of the entire business problem**.
6. **Conversational goal:** follow-ups such as “the first one” or “what about Hanoi?” are target user-experience acceptance cases; they are **not yet verified as supported** by the current implementation.

## Data-source logic

- Real-world conceptual sources: POS/OMS (sales), ERP/WMS (inventory), PIM/Product Catalog (identity/specifications).
- Local demo: synthetic SQLite orders/order_lines/products/inventory/locations and product documents; **no live POS/WMS connectivity**.
- Authoritative calculations: read-only, reviewed SQL and deterministic business rules. Product RAG is not authoritative for stock.
- The month and inventory snapshot timestamp must be disclosed. Stock freshness enforcement is **not yet implemented**.

## Evaluation and open questions

Business acceptance prioritizes **Task Completion Time**, **Task Success/Answer Correctness**, **Interaction Effort** (clicks, filters and switches) and **Ease-of-Use Rating**. Compare equivalent human tool-driven tasks to assisted tasks with a frozen dataset, equal start conditions and independently scored answers. Measure total human task time, not just API latency.

An existing **synthetic CSV pilot** is a rehearsal of this method, **not** a real retailer baseline or a complete usability assessment: its current script records task time, correctness and optional manual steps, but **does not yet record a structured ease-of-use rating**. It must not be presented as measured time savings before participants submit actual results. See [pilot protocol](23_INTERNAL_SYNTHETIC_BUSINESS_PILOT.md).

**Constraints:** five people, ~60 minutes/day/person including coursework, local-only weekly demos, no production, synthetic data only. Week 1 must still demonstrate LangGraph, LangChain SQL, Product RAG, Chain/Agent/Router/Subagent/Handoff/Skill/Custom Workflow, RAGAS and LangSmith with clearly separated live versus mocked evidence; Week 2–4 mandatory course capabilities remain in [requirements baseline](00_PROJECT_REQUIREMENTS.md).

Related: [full business scope](21_INVENTORY_SALES_BUSINESS_SCOPE.md), [PRD](12_Product_Brief_and_PRD.md), [official Week 1 checklist](00_WEEK1_OFFICIAL_CHECKLIST.md).
