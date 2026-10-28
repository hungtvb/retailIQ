# Domain Selection & Business Problem — RetailIQ Copilot

## Domain decision
Official domain **#15 Retail/E-commerce**. Retail product vertical **Electronics & Accessories** retained from preliminary discovery. Earlier B2C online retailer concept is now widened to an **omnichannel** retailer with online sales, two physical stores and one warehouse. The existing order/delivery investigation candidate is deferred to Week 4 Order Management/Fulfilment and possibly Week 2 Order MCP.

## Real-world problem hypothesis (NOT validated)
Inventory planners, store managers and sales managers often need quick, consistent answers to stock and sales questions that require joining multiple transactional reports and reading separate product documents. Fragmented analytics creates manual effort, delays, freshness ambiguity and inconsistent KPI definitions. These are plausible hypotheses, not findings measured at a real electronics retailer.

## Stakeholders
Inventory Manager: available stock across stores and warehouse; Sales Manager: revenue and top-selling SKUs; Merchandising: product specs and descriptions; Retail Ops: cross-channel coordination; Leadership: trustworthy KPIs.

## Reference AS-IS
Question → select inventory/order report or catalog → filter location/channel/date → manually aggregate → interpret policy → present answer. Risks: stale reports, mixing on-hand vs available, mixing ordered vs completed revenue, missing source context.

## Week 1 TO-BE
Natural language question → LangGraph route → (vetted read-only SQL analytic tool) OR (product vector RAG) → sourced, dated answer. LangSmith traces execution; RAGAS evaluates grounded product answers. The assistant is read-only this week.

## Questions/acceptance criteria
- Find available stock by SKU and location; aggregate must equal sum of location availability.
- Revenue this month must use completed orders and a documented definition; group by channel.
- Rank top five products by completed units sold; deterministic tie-breaking.
- Retrieve relevant product specifications and cite product document SKU.
- Provide no fictional data, fake ETA, unverified RAGAS score or fake trace evidence.

## Scope constraints
Team: 5 members × 60 minutes/day including coursework. Local demo only. Use a small local SQLite and product document set; no storefront build, payment gateway, operational data integrations or production deployment.
