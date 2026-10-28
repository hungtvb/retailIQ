# RetailIQ — Business Problem & Decision Support Scope

> **Business direction selected:** Inventory & Sales Decision Support for a synthetic B2C Electronics & Accessories omnichannel retailer.
>
> **Decision date:** 2026-10-28. **Status:** Working business direction selected by project sponsor; workflow assumptions, KPI baselines and acceptance thresholds still require validation by the PO/domain reviewers.
>
> **Scope:** Local-only, four-week AI Flezi mock project. Five team members, approximately 60 minutes per member per day **including study**, with a small demo every week. Preserve the existing learning rubric and working code. No cloud deployment or production integration is required.

## 1. Business problem — not a technology problem

Store and inventory operations staff need to answer questions that combine **stock availability**, **completed-order sales**, and **product identification**. In the *hypothesized* current workflow, they consult several reports/catalog views, reconcile SKU/location/period definitions manually, and then decide whether a best-selling product needs a replenishment review.

That process may be slow, inconsistent or prone to errors. **This pain has not yet been verified with real users or a measured manual-work baseline.** We must validate that before claiming actual time savings, reduced stockouts or ROI.

**Problem statement (candidate for PO approval):** *How might we help a store/retail operations analyst reach a traceable, correctly calculated inventory-and-sales decision from existing read-only information, without manually joining sales reports, inventory snapshots and product records?*

**Primary business outcome:** shorten the effort required to produce a **reviewable stock-versus-sales assessment**, with transparent source facts and a human-owned decision. This is **decision support**, not replenishment optimization or automated purchasing.

### Primary persona and job to be done

- **Primary:** Inventory / Retail Operations Analyst. *When reviewing high-selling products, I need to see which items should be checked for replenishment, with supporting sales quantity and available stock by location, so that I can prioritize a manual review.*
- **Secondary:** Store Operator / Sales Analyst. *When asked about a SKU, current-month performance or specifications, I need a reliable answer traceable to the appropriate source.*
- **Decision owner:** Inventory Manager / Purchasing Manager reviews and decides; RetailIQ does not place purchase orders.

## 2. Single central vertical use case — P0

**UC-01: Review high-selling products against current available stock.**

**Trigger:** An inventory analyst asks, “Which top seller needs a replenishment review based on stock?”

**Input contracts:**

1. Identify top sellers from **completed-order** line quantities for the configured calendar month; ties resolved deterministically by SKU.
2. Resolve the *same exact SKU* against inventory by location.
3. Compute **available = on_hand − reserved** for every valid location; never treat a missing inventory record as zero.
4. Compare the top seller's **monthly units sold** with the current inventory snapshot.
5. Return the evidence (SKU, sales quantity, available by location, totals, source period), a clear **review/not-priority-under-this-heuristic** conclusion and limitations.

**Currently implemented simple screening heuristic:** request a replenishment review when *available units < month-to-date completed-order units sold*. This is only a demonstration heuristic — not a reorder point, demand forecast, safety-stock policy or procurement recommendation. Real decisions require lead time, forecast demand, target service level, inbound stock, returns and current stock freshness.

**Output contract:** read-only and source-backed; if sales data is empty, SKU matching fails, inventory is missing/inconsistent, or timing/freshness cannot support the claim, ask for clarification or abstain rather than invent a decision. If data is present and valid, describe **why** the result was flagged or not flagged. No downstream write side effects.

## 3. As-is / to-be workflow

| Step | As-is (assumption to validate) | To-be with RetailIQ |
|---|---|---|
| 1 | Open current-month sales report | Ask one natural-language question |
| 2 | Manually filter completed orders and identify top products | Reviewed SQL calculates top sellers with fixed metric semantics |
| 3 | Open inventory view and match SKU across locations | Inventory Agent checks the verified top-seller SKU |
| 4 | Subtract reserved stock and compare totals | System computes availability and the limited screening heuristic |
| 5 | Explain the result and provide numbers to a manager | Agent presents cited/traceable evidence and the reason for review |
| 6 | Manager decides whether to investigate/replenish | **Unchanged:** human retains decision and any real purchasing action |

The to-be flow is the business narrative. Whether it saves time/effort remains a hypothesis until observed with users.

## 4. Supporting capabilities and boundaries

| Capability | Priority | Authoritative demo evidence | Business purpose |
|---|---|---|---|
| SKU & multi-location stock lookup | P0 | Synthetic SQLite products + inventory + locations | See physically held vs reserved vs available units |
| Current-month revenue by channel | P0 | Completed synthetic orders and order lines | Make revenue definitions and period explicit |
| Top five products by units sold | P0 | Completed orders; stable SKU tie-break | Identify selling leaders, not margin leaders |
| Stock-vs-sales decision review | **P0 focal use case** | Verified sales and inventory rows | Prioritize manual review using a declared rule |
| Product specifications | P1 supporting | Local product documents; source references | Avoid confusing product documentation with stock truth |
| Multi-turn conversation / handoff | P1 enabling | Local chat session and agent events | Reduce repeated product identification and preserve context |
| Cost/ROI estimate | P2 explanatory | Editable illustrative assumptions only | Discuss potential cost, **not proven savings** |

**Explicit exclusions from this business problem:** customer order-status exceptions/delivery resolution, automatic reordering, order mutations, changing prices, real-time inventory guarantees, demand forecasts, multi-tenant production security, and claiming real business ROI.

These features may appear in the **training rubric for future weeks**, but do **not** redefine this project's primary business problem. Any Week 4 order/approval scenario should demonstrate bounded human approval as a technical training capability, not become a second business initiative.

## 5. Business definitions (minimum semantic layer)

| Concept | Definition for demo | Important caveat |
|---|---|---|
| As-of month | Month selected by `RETAILIQ_AS_OF` (default 2026-10) | Synthetic fixed reference period, not the user's real-time “now” |
| Available stock | `on_hand - reserved`, summed for a specific SKU across valid locations | Snapshot, **no freshness SLA** |
| Revenue | `SUM(quantity × unit_price_vnd − discount_vnd)` on `completed` orders in month, by channel | Integer VND; before returns, tax, shipping |
| Top seller | Five highest completed-order quantities in month; ties by SKU | Units, not profitability or trend |
| Replenishment review | For verified top-SKU only: flag when `available < units_sold` | Teaching heuristic; not a procurement calculation |
| Product facts | Retrieved local product documents with provenance | Product docs do not certify stock availability |

## 6. Business KPI framework — validation comes first

| Business KPI | How to measure | Current status |
|---|---|---|
| Time-to-insight | Stopwatch: from receiving UC-01 question to producing a correct evidence-backed review; compare same tasks manually vs RetailIQ | **Baseline not measured** |
| Answer/data correctness | Golden-case match of SKU, completed-order count/quantity, money, location and availability vs independent SQL oracle | Synthetic checks exist; business acceptance threshold not approved |
| Traceability rate | Fraction of accepted decisions with explicit source month, SKU, sales quantity and inventory evidence | Baseline/target pending review |
| Manual steps per review | Count report switches, filters, lookups and calculations for equivalent manual-vs-assisted tasks | Baseline not measured |
| Safe abstention rate | Invalid/ambiguous/stale/missing data cases where system does not fabricate a confident conclusion | Negative cases to expand |
| Human decision usefulness | Blind review of explanation/actionability by an inventory-domain reviewer | External reviewer not recruited |

**Proposed mini-pilot:** prepare 10–20 deterministic golden questions, 3–5 realistic decision scenarios (including no-stock, ambiguous SKU, cancelled orders, low stock, sufficient stock), and ask a domain reviewer to compare manual versus assisted outcomes. Set quantitative success thresholds **after** collecting a first baseline; no invented 30%/60% benefits.

**Separate engineering metrics** (latency p50/p95, error rate, throughput) are technical health evidence, not business value or measured ROI. See [local E2E and benchmark evidence](20_LOCAL_E2E_BENCHMARK_EVIDENCE.md).

## 7. Synthetic dataset: what we have and what is needed

**Current seeded baseline:** 10 products, 3 locations, 30 inventory rows, 120 orders, with product documents and one reference month. Designed for repeatability, not statistical representativeness.

**Business QA cases to add *only if necessary* for the weekly scenario:**

1. A top seller with low-but-valid available stock (screening result is review).
2. A top seller with adequate available stock (screening result is no immediate priority).
3. Zero completed orders in period (no fabricated top seller).
4. Cancelled order and discounted order lines (valid revenue/sales filters).
5. Missing/inconsistent stock evidence (abstain) and unknown/ambiguous SKU (clarify).
6. Previous-month/December rollover boundary; stale inventory timestamp clearly visible.

Keep these as small test-only fixtures, not a second large dataset or a new integration architecture.

## 8. Four-week business narrative, fitted to the training course

| Week | One incremental business slice | Demo proof and deferred work |
|---|---|---|
| **1** | Ask for top sellers, current available stock and a transparent review suggestion | Real read-only SQL results + local UI, source period and calculations; mock vs full LangGraph/provider clearly labeled |
| **2** | Make the same answer reliable when sources differ in recency or definition | Freshness badge/abstention and governed KPI contract; narrowly scoped MCP read operations if rubric requires, no order writes |
| **3** | Show that the recommendation is governable | Approval/acknowledgement demo, safe logs, permissions/constrained action, cost evaluation; no autonomous purchase |
| **4** | Present one verified multi-agent replenishment **review case** | Cross-specialist evidence and verification report; mock/human approval for any hypothetical order action, while complying with required training agent patterns |

**Delivery principle:** demo one small vertical slice every week; reuse the Week 1 data/API/agent paths, limit work to team capacity, defer optional features when baseline demo/tests are unstable.

## 9. Acceptance gates / business decisions still open

- **Scope selected:** Inventory & Sales Decision Support. **Not selected:** Order Status & Delivery Exception Resolution.
- **Technical local demo:** deterministic and mocked E2E/benchmark evidence exists; see [quality evidence](20_LOCAL_E2E_BENCHMARK_EVIDENCE.md). It does not certify model accuracy.
- **Business validation:** persona interviews/observations, as-is timing, priority of scenarios, expected accuracy and reviewer sign-off — **PENDING**.
- **Live-model credibility:** real OpenAI-compatible model/Chroma, RAGAS semantic evaluation and LangSmith traces — **NOT VERIFIED** until independent evidence is captured.
- **Future expansion gate:** do not broaden to fulfilment/order-resolution or automated actions unless a new business problem and capacity trade-off are explicitly approved.

## Source of truth

- [Product Brief and Week 1 PRD](12_Product_Brief_and_PRD.md)
- [Data and API definitions](13_Data_and_API_Contract.md)
- [Four-week course requirements](00_PROJECT_REQUIREMENTS.md)
- [Four-week implementation roadmap](16_Roadmap_and_Timeline.md)
- [Business Golden Scenarios — synthetic acceptance register](22_BUSINESS_GOLDEN_SCENARIOS.md)
- [Internal synthetic-data usability pilot — data, counterbalanced task sheet and non-fabricated analysis](23_INTERNAL_SYNTHETIC_BUSINESS_PILOT.md)
- [Local E2E and benchmark](20_LOCAL_E2E_BENCHMARK_EVIDENCE.md)
