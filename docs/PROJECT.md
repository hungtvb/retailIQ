# RetailIQ — Product Overview

## Purpose

RetailIQ is a **retail decision-support copilot** for B2C electronics and accessories operations. Users ask natural-language questions across inventory, sales, orders and product knowledge, then receive answers whose business facts and sources can be checked.

**Faster · Easier · Reliable** are product goals, **not measured achievements**. RetailIQ supports human decisions; sensitive pricing or order changes require governed execution and approval rather than unchecked autonomous actions.

## Business problem

Retail staff may have to move between POS/OMS, ERP/WMS, product catalogs, knowledge documents and reporting screens to complete one operational task. Filters, KPI definitions, source freshness and product identity may differ across those systems. Combining and validating the resulting information takes effort and can produce inconsistent answers.

**Problem statement:** Retrieving, combining and verifying retail operational information can require multi-step interaction across tools and data sources, particularly when a decision depends on exact SKU, time period, location or policy.

This is a **hypothesis derived from an illustrative retail scenario**, not a finding established by interviews, observation or measurement in a real retailer. A conventional report or dashboard may already be better for a simple lookup.

## Users and jobs

| User | Job to be done |
|---|---|
| **Store / retail operations staff** (primary) | Check product details, stock availability and related operational information without unnecessary navigation |
| **Store / retail managers** | Compare sales results across products, periods and locations, then review supporting facts |
| **Inventory / sales analysts** | Combine sales performance and inventory to identify items needing human review |
| **Order operations managers** (extended workflows) | Examine fulfillment/pricing/order proposals and approve sensitive decisions within an authorized process |

Typical questions include: available stock by SKU/location; revenue for a specified month; top-selling products; product specifications and compatibility; and stock of a previously identified top seller. Conversational follow-ups must preserve the requested entities, period and location. These examples define intended coverage, **not proof that every phrasing currently works**.

## Product scope

**Core experience:** natural-language information access, business analytics, source-grounded product answers, context-aware follow-ups, and explanations sufficient for verification.

**Extended experience:** cross-source decision-support workflows, freshness/source selection, consented memory, governed approvals and specialist-agent coordination. The [requirements](REQUIREMENTS.md) specify the required capabilities; the [course roadmap](COURSE_PLAN.md) retains the original sequence.

**Out of scope unless explicitly specified:** production commerce transactions, real retailer integrations, unauthenticated autonomous pricing or ordering, and claims that a displayed role/graph node is an independently acting AI agent.

## Intended outcomes and validation

| Goal | Evaluation method | Current evidence |
|---|---|---|
| **Faster** — less time to a correct, checked answer | Measure end-to-end task time **including** retries, model latency and human verification against the equivalent manual-tool workflow | No real-user baseline or demonstrated time saving |
| **Easier** — lower interaction effort | Count filters, clicks and system switches; collect a short 1–5 ease-of-use rating on comparable tasks | Not validated with real users |
| **Reliable** — correct and auditable business information | Check against an independent SQL/data oracle; verify SKU/period/location, source citations and safe clarification/abstention | Local synthetic scenarios exist; this is not provider-wide or production reliability |

The comparison should use a frozen dataset, the same business tasks and an independently checked answer key for both approaches. Report failures and corrections rather than only successful queries.

## Decision boundaries

- Prefer a direct trusted data query over an additional agent for simple tasks; use orchestration only when cross-source dependencies or control flow justify it.
- Never silently change SKU, reporting period, rank, location, channel or authorization scope to produce an answer.
- Transactional metrics require authoritative structured data; product-document facts require referenced source documents. Product documents cannot establish live stock availability.
- Managers remain responsible for sensitive business approvals. The current local synthetic implementation and deterministic workflow simulations do not establish production authorization or financial ROI.

## Related information

[Requirements](REQUIREMENTS.md) · [Architecture](ARCHITECTURE.md) · [Data/API definitions](DATA_API.md) · [Roadmap](COURSE_PLAN.md)

Historical discovery notes and earlier scope drafts are retained in [archived business analysis](archive/2026-10-30/legacy/21_INVENTORY_SALES_BUSINESS_SCOPE.md) and the [original PRD](archive/2026-10-30/legacy/12_Product_Brief_and_PRD.md).
