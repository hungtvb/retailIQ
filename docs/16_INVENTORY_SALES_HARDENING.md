# Inventory & Sales — Business Invariants and Failure-Mode Tests

**Status:** Code changes on main; local reconstructed-source regression passed. Live provider/compiled graph and GitHub CI results must be checked separately.

## Business contracts

### Inventory

Input: a known SKU (case-insensitive ASCII identifier, 1–64 characters; internal whitespace trimmed at edges). Output: read-only records per location, ordered by location ID. A missing inventory record set is **empty evidence**, not numeric zero.

Invariants:
- \`available = on_hand − reserved\`, with \`on_hand\`, \`reserved\`, \`available\` all non-negative integers.
- A product SKU must match the requested identifier and have one row per actual \`location_id\`.
- Product and location names are nonempty, and \`updated_at\` parses as a timezone-aware timestamp.
- Orphaned location data is detected instead of silently disappearing through an inner join.
- Timestamp **validity** is enforced; enforcing freshness SLA and time-based source selection is reserved for Week 2.
- Invalid state raises \`DomainDataError\` (permanent business-data failure). SQL operational errors propagate for retry classification by the harness.

### Sales

Input: \`RETAILIQ_AS_OF\` ISO date. Queries use the calendar-month range \`[YYYY-MM-01, next-month-01)\`; this handles December/January and ISO-style timestamps in the fixture.

Invariants:
- Only \`completed\` orders contribute; canceled orders and other months do not.
- Net revenue uses integer VND: \`SUM(quantity × unit_price_vnd − discount_vnd)\`. The discount is **per order line**, not per unit; returns/refunds are **not modeled**, so the figure is before returns.
- Completed-order line quantity must be a positive integer, price/discount nonnegative integers, discount no greater than the line's gross value. Orphan product references fail closed.
- Revenue grouping is by channel, with distinct completed-order counts for channels that have lines.
- Top seller ranking uses units sold descending and SKU ascending to break ties, max five products. No model-invented rankings.
- Invalid source rows raise \`DomainDataError\`. An empty period has no records and is reported explicitly as no completed-order data.

### Cross-domain Replenishment

A sales winner without inventory evidence **cannot** produce a purchasing recommendation. The screening heuristic remains Week 1 read-only; no PO, forecasting, or approval is introduced.

## Failure-mode coverage

| Case | Expected outcome |
|---|---|
| Known SKU with valid on-hand and reservations | Exact per-location arithmetic |
| Valid SKU with no stock records | Explicit lack-of-evidence answer; no IndexError and no fabricated 0 |
| Malformed SKU or injection-like identifier | Immediate validation failure |
| Reserved exceeds on-hand / negative or text stock quantities | \`DomainDataError\` |
| Duplicate or orphan location | \`DomainDataError\`, not a silently dropped row |
| Bad or timezone-naive inventory timestamp | \`DomainDataError\` |
| DB locked / operational failure | Propagates; never returned as stock=0 |
| Completed, canceled, previous/next month orders | Only completed orders in requested month counted |
| Two products with identical units sold | Stable SKU tie-breaker |
| Missing quantity, text price, impossible discount, orphan product | Report rejected, no misleading KPI |
| No completed orders | Empty results with explicit no-data wording |
| No inventory for top seller | No replenishment assessment |
| Domain invariant failure | Non-retryable under Week 1 transient SQL retry policy |

## Evidence

- \`tests/test_inventory_sales_hardening.py\`: parameterized, real SQLite fixtures covering happy paths, negative and zero stock, date boundaries, SQL failures, source corruption, zero/empty data, deterministic ranking, and missing evidence.
- \`retailiq/domain/analytics.py\`: reviewed queries and typed validation.
- \`retailiq/assistant.py\`: safe business-facing no-data outcomes.
- On the reconstructed local source snapshot with patches applied, \`RETAILIQ_MODE=offline python -m pytest -q -k 'not test_no_retry_for_source_business_invariant'\` resulted in **123 PASS, 1 SKIP, 1 deselected**. The deselected test imports a newer retry policy implementation present on GitHub main but absent from the local snapshot. **Do not report this as full main-branch CI PASS.**
- For authoritative CI verification, run \`python -m pytest -q -rs\` with \`requirements-full.txt\` on the current GitHub main; \`RETAILIQ_REQUIRE_LANGGRAPH=true\` must prevent skipping the graph module.

## Remaining engineering decisions

- A late-arriving or stale source snapshot is not automatically rejected yet; source freshness guarantees belong to Week 2.
- SQLite stores prices in integer VND (no floating-point currency arithmetic); real returns/refunds, tax, settlement currency, and cross-timezone business calendar definitions require a real retailer's semantic model.
- Data validation adds a small reviewed SQL preflight for each sales report. Benchmark with larger datasets before making performance claims.
- SQL access controls are local read-only safeguards, not production tenant authorization.
