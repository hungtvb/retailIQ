# RetailIQ Copilot — Business Problem (Week 1)

> **Domain:** Retail / E-commerce — B2C Electronics & Accessories  
> **Business setting:** An illustrative omnichannel retailer with an online channel, two physical stores, and a central warehouse.  
> **Evidence status:** Working business hypothesis, selected on 2026-10-28; **not validated through interviews or observation of real retailer users**.  
> **Purpose:** Address the three Business Problem evaluation checkpoints: problem clarity, users and pain points, expected value and impact.

## At a glance

**The challenge:** Retail information exists, but getting a *correct, usable answer* to a business question may require multiple screens, reports, filters, and data sources.

**The opportunity:** Make those information tasks **Faster · Easier · Reliable** through a natural-language retail copilot that uses trusted data and shows the basis of its answers.

**The boundary:** RetailIQ assists information retrieval, analysis, and human decision-making; it is not an autonomous purchasing or price-changing system in Week 1.

---

## 1. Clearly identify the business problem

### Business context

Store and retail operations teams work with sales transactions, stock levels, product catalogs, and product documentation. Existing POS, OMS, ERP/WMS, BI, and product-management tools may already contain this information. The difficulty is not necessarily a lack of software or data; it is the effort required to navigate and connect the right information for a particular question.

### Problem statement

> **Retail business users face complex, multi-step interactions across existing tools and data sources when retrieving, combining, and analyzing operational information.** This can increase time-to-answer and user effort, while creating opportunities for inconsistent metrics, mismatched products or locations, and answers that are difficult to verify.

Consider a manager asking:

> “Which products sold the most this month, and how much stock do we have for the top product in Hanoi?”

In a conventional tool-driven workflow, the user may need to:

1. Open a sales report, select the correct month and order statuses, and identify top-selling products.
2. Find the product's exact SKU rather than relying on a similar product name.
3. Open an inventory view and filter by that SKU and the Hanoi location.
4. Compare the results, confirm the reporting period and stock snapshot, and prepare an answer.

These are **illustrative tasks**, not observations from an actual retailer. Some organizations already provide such information in a single dashboard.

### Why it matters

| Business friction | Consequence for the user |
|---|---|
| Switching between reports, screens, or systems | More navigation and repeated filtering |
| Understanding different data structures and KPI definitions | Higher learning burden; potential interpretation errors |
| Matching SKU, time period, location, and order status | Risk of comparing the wrong records |
| Combining sales, inventory, and product facts | More steps before a decision-support answer is available |
| Limited visibility into the basis of an answer | Extra time needed to check or challenge the result |

**This is not a “revenue-query problem,” a “lack of AI problem,” or exclusively a replenishment problem.** Those are examples within the broader problem of accessing and understanding retail information.

---

## 2. Understand the target users and their pain points

### Primary and secondary users

| User | What they need to accomplish | Main pain point |
|---|---|---|
| **Store / Retail Operations Staff — primary** | Check available stock, product details, and relevant sales information during daily work | Repeating navigation and filters across different views; unfamiliarity with data fields or reporting tools |
| **Store / Retail Manager** | Understand store performance and answer operational questions quickly | Comparing periods, locations, products, and metrics before making a decision |
| **Sales / Inventory Analyst or Manager** | Review top sellers, available inventory, and possible stock issues using consistent definitions | Reconciling sales and stock records while preserving exact SKU and location identity |

These personas are **assumptions for the mock project**, not validated interview findings. Managers remain accountable for business decisions and approvals.

### Core job to be done

> **When** I need sales, inventory, or product information to perform an operational task, **I want** to ask a question in plain language and receive a clear, checked answer with relevant supporting facts, **so that** I can complete the task without unnecessary tool navigation or having to understand database schemas.

### Representative business questions

- **Inventory:** “How many units of this product are available, and where?”
- **Sales:** “What is revenue for the selected month?”
- **Performance:** “Which five products sold the most units this month?”
- **Product knowledge:** “What are the specifications or compatibility details of this product?”
- **Cross-source review:** “For a top-selling product, what stock is available across locations?”
- **Conversational follow-up (experience target):** “What about the first product in Hanoi?”

The examples describe the **business coverage and desired interaction**, not a claim that every phrasing or follow-up already works in the current implementation.

---

## 3. Explain the expected value, benefits, and business impact

RetailIQ proposes one conversational entry point for retail questions. Behind that interface, trusted numerical data and product information would be selected, combined when necessary, and returned with enough context for a person to verify the result.

### Expected outcomes

| Outcome | Expected user benefit | How we would measure it |
|---|---|---|
| **Faster** | Less end-to-end time needed to reach a *correct, checked* answer | **Task Completion Time:** question received → user verifies final answer, including corrections or retries |
| **Easier** | Fewer clicks, filters, screen switches, and less knowledge of report structures | **Interaction Effort:** clicks, filters, tool/screen switches; **Ease-of-Use Rating** after each task |
| **Reliable** | Correct numbers, consistent KPI definitions, exact SKU/period/location matching, and visible sources or limits | **Task Success / Answer Correctness**, evidence coverage, and safe clarification when information is ambiguous or missing |

**Business impact, if the hypothesis is validated:** less operational effort spent gathering information, more consistent interpretation of retail data, and a simpler path to evidence-based decisions. These are **anticipated benefits**, not measured savings or ROI.

### Illustrative before-and-after experience

| AS-IS — user operates existing tools | TO-BE — RetailIQ-assisted task |
|---|---|
| Locate the relevant report and choose filters | Ask the question in natural language |
| Open another screen to find related stock or product data | Route to the relevant trusted information sources |
| Match products, locations, and reporting periods | Preserve and verify identifiers and reporting context |
| Interpret figures and manually prepare a response | Present a readable answer with supporting facts and limitations |
| Verify the result and make a business decision | **Still required:** user verifies; manager approves sensitive decisions |

Natural language is **not automatically faster**. Model latency, clarification, and verification can offset time saved on navigation. Correctness takes precedence over a fast but unsupported answer.

### How we will validate business value

Use the **same frozen synthetic dataset and independently checked answer key** for comparable tasks completed through a manual tool-driven path and through RetailIQ. Capture task time, correctness, number of interaction steps, corrections, and a short 1–5 ease-of-use rating. Report failures rather than excluding them from the comparison.

**Current evidence boundary:** No real retailer baseline, validated time saving, ease-of-use improvement, or realized financial ROI has been established. The existing internal synthetic pilot is a rehearsal, not proof of business impact. Its current instrumentation does not yet cover the full ease-of-use measurement.

---

## Business scope and constraints

**Week 1:** The information-access problem is demonstrated through four required areas—**inventory, monthly revenue, top-selling products, and sourced product details**—plus an illustrative cross-source review. Answers are read-only, using synthetic local data and documents. No live retailer integrations or autonomous business mutations are claimed.

**Weeks 2–4:** The original course requirements remain intact, including MCP, freshness and memory; governance and human approval; and the five-agent order/fulfilment/pricing scenario. A replenishment review is only one example and does **not** replace the full Week 4 order scenario.

**Delivery context:** Five-person team, local-only weekly demos, approximately 60 minutes per person per day including learning. This document defines the **business need**, not the technical architecture or implementation-completion status.

## Week 1 evaluation checklist mapping

| Business Problem checkpoint | Where it is addressed |
|---|---|
| **1. Clearly identify the problem to be solved** | Section 1: context, problem statement, example, business friction |
| **2. Understand the target users and their pain points** | Section 2: primary and secondary personas, jobs to be done, user questions |
| **3. Explain the expected value, benefits, or business impact** | Section 3: Faster · Easier · Reliable, expected impact, measurable validation |

## Related documents

- [Full business scope and outcomes](PROJECT.md)
- [Week 1 Product Brief / PRD](PROJECT.md)
- [Four-week course requirements](COURSE_PLAN.md)
- [Week 1 official presentation checklist](weeks/week-01/README.md)
- [Internal synthetic business pilot](weeks/week-01/EVIDENCE.md)
- [Solution architecture](ARCHITECTURE.md)

## Decision and business-acceptance guardrails

Inventory and Sales are initial domains—not the complete RetailIQ problem. Replenishment Review is only a cross-source demonstration, not autonomous procurement. Staff must verify facts; managers retain sensitive action approval. No measured business ROI or retailer user-research baseline exists yet.

The detailed user stories, persona assumptions and initial scope decisions remain accessible in the [historical PRD](archive/2026-10-30/legacy/12_Product_Brief_and_PRD.md) and [expanded business analysis](archive/2026-10-30/legacy/21_INVENTORY_SALES_BUSINESS_SCOPE.md). The current weekly acceptance criteria belong to [Week 1](weeks/week-01/README.md), not this evergreen business statement.
