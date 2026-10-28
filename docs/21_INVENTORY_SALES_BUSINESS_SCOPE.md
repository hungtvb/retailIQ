# RetailIQ — Business Problem, Outcomes & Inventory/Sales Scope

> **Business direction confirmed by sponsor:** **Faster · Easier · Reliable access to retail operational information through natural-language interaction**, using Inventory & Sales as the initial domain and Replenishment Review as a cross-source illustration.
>
> **Decision date:** 2026-10-28. **Status:** Sponsor direction selected; retailer user workflow, baseline KPI values, acceptance thresholds and PO/domain sign-off **not validated**.
>
> **Delivery boundaries:** Four-week AI Flezi local mock project; five team members, ~60 minutes/person/day **including study**, incremental weekly demos, synthetic data, no cloud/production deployment. The official course rubric is unchanged.

## 1. Business problem — not “lack of AI” or “lack of tools”

Retail staff may already use POS, OMS, ERP/WMS, product catalogs, spreadsheets and BI. A single operational question can require the user to navigate several screens or separate systems, choose filters and periods, reconcile product SKU/location identifiers and combine results.

**Business problem statement:** *Retail business users face complex, multi-step interactions across operational tools and data sources when retrieving, combining and analyzing retail information. These workflows can increase user effort and time-to-insight, while making consistent, evidence-based answers harder to obtain.*

**Manual** here means **human-operated work within existing tools**: clicking, filtering, switching screens, exporting, joining and interpreting results, **not** that staff have no software. Some mature retailers already automate KPI reports and replenishment. This is a **working hypothesis**, not evidence gathered from real store staff.

**Solution hypothesis:** RetailIQ offers a unified **natural-language conversational interface** that selects trusted read-only data tools, coordinates cross-source questions and returns intelligible answers with verifiable data evidence. A dashboard might already solve straightforward questions; we must test whether natural-language interaction adds value for multi-step/contextual tasks.

## 2. Business objectives and proposed measurements

| Priority | Objective | Observable KPI | Required interpretation |
|---|---|---|---|
| **P0 Faster** | Reduce effort-to-answer latency for an equivalent business task | **Task Completion Time**, measured from question receipt until a completed, checked answer; report failed/retry tasks separately | Target/hypothesis only; no demonstrated improvement yet |
| **P0 Easier** | Reduce effort navigating reports, filters and multiple tools | **Interaction Effort** (clicks, filters, screens/tool switches); **Ease-of-Use Rating** (e.g. post-task 1–5) | Fewer steps does not automatically mean faster |
| **P0 Reliable** | Return correct and traceable results | **Task Success Rate**, **Answer/Data Correctness**, source/period/SKU traceability and safe abstention | Wrong/unsupported answers cannot count as successful |
| Supporting | Improve first-use accessibility | First-attempt success, help requests and learning effort | Optional qualitative pilot within team capacity |

**Time-to-insight is a user task metric, not API p95.** Network/model execution, clarification, reviewing evidence and the user's final response all count. Assess correctness alongside time: a fast wrong answer is not business value.

**Evidence status:** No real retailer timing, usability baseline, cost saving, business ROI or externally validated usability gain. Internal synthetic volunteers can provide **exploratory usability observations** only.

## 3. User and jobs to be done

- **Primary persona:** Store/Retail Operations Analyst (assumed). *When I need stock, sales or product information, I want to ask in natural language and follow up without repeatedly navigating dashboards or knowing database schemas, so I can complete the task with less effort and receive reliable evidence.*
- **Secondary:** Inventory analyst/manager. *When comparing fast-selling products with location inventory, I need a traceable assessment to decide which SKU merits review.*
- **Decision owner:** Manager or buyer retains any purchasing/stock-change decision. Week 1 is strictly read-only.
- **Domain sign-off:** pending actual user/PO review.

## 4. Business scenarios — breadth and focused vertical slice

| Scenario | Example user question | Data/tool path | Business value |
|---|---|---|---|
| UC-A Stock lookup | How many units of Product A are available by location? | Inventory + Product Master SQL | Fewer inventory-view lookups |
| UC-B Sales metrics | What is revenue this month? | Completed-order sales SQL | Consistent metric semantics |
| UC-C Product ranking | Which SKUs are top sellers? | Sales SQL | Natural-language ranking |
| UC-D Product knowledge | Does this charger support 65W PD? | Product RAG + document evidence | Search documents without manual browsing |
| **UC-E Multi-source review (featured)** | Which top seller needs replenishment review? | Sales → verified SKU → Inventory → deterministic business rule | Demonstrate orchestration of multiple existing sources |
| **UC-F Contextual follow-up (target)** | How much stock does the first one have? What about Hanoi? | Conversation referent + filtered inventory | Demonstrate reduced re-entry/navigation; not all phrasing supported today |

**UC-E is the featured read-only multi-agent demonstration, not the sole business problem.** UC-A through UC-D are the four required Week 1 questions; UC-F is a desired experience that must be tested independently, not assumed implemented.

### UC-E business contract (existing limited implementation)

1. Retrieve highest-selling SKU from **completed** order lines in the configured calendar month, with deterministic SKU tie-break.
2. Use that **exact SKU** for per-location inventory lookup; no fuzzy joining on product name.
3. Validate available units = on_hand − reserved; missing rows are **unknown**, not zero.
4. Flag **manual review** iff current total available units < month-to-date completed units sold.
5. Present SKU, reporting month, sold/available figures, source/location evidence and a clear limitation. Never create a purchase order.

This is a **classroom screening heuristic**, not demand forecasting, a professional reorder point or an actual shortage prediction. Lead time, inbound orders, seasonality, safety stock, returns and production freshness are not modeled. A stale inventory timestamp currently **does not trigger rejection**; freshness-aware behavior is a Week 2 gap.

## 5. AS-IS / TO-BE and tool/agent rationale

| Human-driven AS-IS (hypothetical) | Proposed RetailIQ TO-BE |
|---|---|
| Open sales/POS/BI report, set period and status filters | Ask for top sellers/revenue in natural language |
| Navigate to WMS/ERP inventory, match SKU and location | Use Sales/Inventory tools with verified SKU identity |
| Consult product documents separately | Use Product RAG with retrieved source references |
| Combine/interpret, repeat steps for follow-up questions | Route simple questions to one tool; coordinate multiple tools only when needed |
| Verify output, request approval/action | **Unchanged**: user verifies evidence; manager approves any sensitive real action |

**Tool-first, agent-second, workflow-driven:** Sales Tools perform reviewed numerical queries; Inventory Tool returns stock evidence; Product retrieval uses RAG; Supervisor orchestrates UC-E; deterministic verification checks numbers and source identity. A simple question should not require multiple agents. Week 1 agent patterns are demonstrated by actual appropriate paths rather than simulated labels.

**Example intended conversation:** “Which products are top sellers?” → “How much stock do we have for the first one?” → “What about Hanoi?” → “Should we review replenishment?” This is an **experience target**, not a claim that all four follow-ups work today.

## 6. Data Sources and authoritative facts

| Conceptual real-world source | Synthetic local equivalent | Trusted for | Limit |
|---|---|---|---|
| POS/OMS sales transactions | SQLite orders + order_lines | Completed units sold, revenue, ranking | Fixed reference month, no production sales |
| ERP/WMS inventory | SQLite inventory + locations | On-hand, reserved, availability, updated_at | Snapshot only, no enforced freshness SLA |
| PIM/Product Master | SQLite products | Exact SKU, name/category/price reference | Synthetic catalog |
| Product knowledge/docs | Local product documents + offline lexical/full-mode vector retrieval | Product specifications with provenance | **Not** authoritative for current stock |

**Semantic definitions:** revenue = sum(quantity × unit_price_vnd − discount_vnd) for completed orders in month (VND, before returns/tax/shipping); top five = completed-order units, SKU tie-break; available = on_hand − reserved by location; reference month selected by RETAILIQ_AS_OF (default October 2026). **All calculations occur in reviewed SQL/domain logic**, not free-form model arithmetic.

## 7. Business validation plan and present measurement gap

- **User-task benchmark:** assign equivalent questions for a manual workflow (existing tool navigation; the current pack uses CSV/Excel as a **proxy**) and RetailIQ; randomize/counterbalance task assignment, freeze dataset and use an independent answer key.
- **Capture:** time from question receipt to user's verified final answer; pass/fail correctness, corrections and retries; number of filters/clicks/tool switches; a 1–5 post-task ease rating with qualitative notes.
- **Report:** task success and correctness **first**, then completion time (including failures/retries in the analysis), effort and ease ratings. Do not generalize from small synthetic volunteer samples.
- **Current code gap:** [pilot export/analyzer](23_INTERNAL_SYNTHETIC_BUSINESS_PILOT.md) can record duration, correctness and optional manual steps; it does **not** yet natively capture ease-of-use rating, detailed interaction counts, or a robust end-to-end comparison against actual POS/WMS UIs. Update the study instrument before claiming Easier has been quantified.
- **Engineering gates** such as API latency p95, mocked E2E pass rate and test count **cannot substitute** for human business outcomes.

**Status:** real financial ROI, time savings, ease-of-use lift and retailer impact **not measured**. We must not imply an internal synthetic experiment proves them.

## 8. Four-week business narrative — preserve course requirements

| Week | Demoable incremental vertical slice | Mandatory course capability boundary |
|---|---|---|
| **1 — Ask & Retrieve** | Stock, revenue, top sellers and sourced product answers; one cross-source review case; basic follow-up | **LangGraph, SQL Tools, Product RAG/VectorDB, RAGAS, LangSmith**, Harness and **Chain/Agent/Router/Subagent/Handoff/Skill/Custom Workflow** evidence; live vs mocked distinguished |
| **2 — Connect & Understand** | Freshness/KPI source contracts, context improvement and governed read access | Freshness-aware routing, semantic layer, **MCP Inventory + Order APIs**, customer context memory, advanced retrieval/hybrid/rerank |
| **3 — Control & Trust** | Guarded interactions and measurable operational confidence | Human approval, access controls, KPI alerts, token cost, **Langfuse**, **DeepEval**, security/PromptOps governance |
| **4 — Coordinate & Act** | Full mock order scenario with cross-agent collaboration and manager approval | **Five required specialist agents**: Inventory Search, Fulfilment Optimisation, Customer Context, Dynamic Pricing, Order Management; A2A-style coordination, verification loop, deep decision report |

**Do not replace the Week 4 full order/approval scenario with only a replenishment review.** It is a course requirement even though the business problem remains natural-language simplification. Keep sample size/features small enough for the five-person timebox; no unauthorized real writes or production deployment.

## 9. Status, boundaries and source of truth

- **Implemented/tested locally:** Synthetic SQL data contracts; domain lookup and calculation tests; selected Router/Subagent/Handoff/Skill patterns in code; mocked compiled graph paths. These do not certify a live LLM.
- **Not yet verified:** Real provider/Chroma end-to-end run, RAGAS score and LangSmith trace, retailer-based UX baseline, target KPI achievement, freshness policy, unrestricted contextual references.
- **Explicit non-goals Week 1:** automatic ordering, price changes, stock writes, live POS/WMS integrations, demand forecasting, production auth/SLAs and real business ROI.
- **Stakeholder actions:** agree persona and business objective measurements; verify end-user workflows if available; retain honest evidence distinctions.

References: [Domain & initial problem](01_Domain_Selection_and_Business_Problem.md), [Product Brief/PRD](12_Product_Brief_and_PRD.md), [Data/API contract](13_Data_and_API_Contract.md), [Official course requirements](00_PROJECT_REQUIREMENTS.md), [Week 1 checklist](00_WEEK1_OFFICIAL_CHECKLIST.md), [Golden business scenarios](22_BUSINESS_GOLDEN_SCENARIOS.md), [Internal synthetic pilot](23_INTERNAL_SYNTHETIC_BUSINESS_PILOT.md), [Traceability](14_Requirements_Traceability.md), [Local E2E evidence](20_LOCAL_E2E_BENCHMARK_EVIDENCE.md).
