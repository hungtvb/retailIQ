# UC-03 — Sales & Inventory Analysis · Implementation Detail (Proposed)

**Approval gate:** This document is a **proposed design**, not proof of implementation or an approved code contract. Review and merge its documentation PR to \`main\` before feature coding; implementation Issues/PRs must cite the merged design commit SHA.
**Source baseline:** RetailIQ Fiction M0 ([#31](https://github.com/hungtvb/retailIQ/issues/31), [PR #33](https://github.com/hungtvb/retailIQ/pull/33)); Fiction \`fiction-retail-unified-v1.0.0\` (local immutable SQLite + manifest).
**Priority:** UC-03 follows [UC-01 Backorder Investigation #34](https://github.com/hungtvb/retailIQ/issues/34) and [UC-02 Refund Reconciliation #35](https://github.com/hungtvb/retailIQ/issues/35). Design work does **not** reprioritize their unfinished integration/E2E acceptance.

**Canonical references:** [Basic Design](../DESIGN.md) · [Fiction runtime](../FICTION_RUNTIME.md) · [Data/API](../DATA_API.md) · [Fiction Data Contract](https://github.com/hungtvb/fiction-retail/blob/main/docs/DATA_CONTRACT.md) · [Orchestration #23](https://github.com/hungtvb/retailIQ/issues/23) · [Context #22](https://github.com/hungtvb/retailIQ/issues/22) · [Evidence #28](https://github.com/hungtvb/retailIQ/issues/28) · [UI/E2E #30](https://github.com/hungtvb/retailIQ/issues/30).

## 1. Goal, question and scope

**User job:** “Trong tháng 10/2026, 5 sản phẩm bán chạy nhất theo số lượng trên các đơn hiện có trạng thái delivered là gì? Tồn kho **được ghi nhận** của những sản phẩm đó ở từng kho ra sao; trường hợp nào cần nhân viên xác minh thêm?”

**Outcome:** A read-only, source-linked **cross-domain** result that (a) ranks products for a precisely defined sales period, (b) binds each ranked \`product_id\` / \`sku\` to the correct inventory rows and warehouse IDs, (c) separates measured facts from screening observations, and (d) explains missing evidence and temporal limitations. Support one trusted same-session follow-up (“tồn kho của sản phẩm đứng đầu tại kho nào?”) without changing the selected product or sales period.

**In:** month + rank/limit; exact per-product inventory across recorded warehouse rows or an explicitly verified warehouse UUID; source release, identity, period, quantity and row/aggregate evidence; bounded multi-capability execution and answer verification.

**Out:** live stock/stockout claims, “inventory at the sales-month end”, forecasting, days-of-cover, replenishment quantities, purchasing/transfers or writes, automatic warehouse allocation, warehouse/channel-level *sales* ranking without a trusted attribution contract, a new agent framework or separate Sales/Inventory services. Product guide RAG and policy lookup are **not required** by this UC's first slice.

**Business value vs simple lookup:** A single top-seller or SKU-stock question can use one trusted query; this UC specifically verifies dependent **Sales → canonical product identity → Inventory** handoff. No claims of time saving or improved decisions without measurements.

## 2. Proposed execution (not yet wired)

~~~mermaid
flowchart TD
    U[Operator: month and top N] --> API[Existing /ask or /ask/stream]
    API --> CX[Resolve explicit or committed same-session period and rank]
    CX --> PLAN[Validate registered bounded read-only task plan]
    PLAN --> SALES[FictionStore.top_sellers month and limit]
    SALES --> CHECK{Valid source, period, rank, product IDs?}
    CHECK -->|No| STOP[Clarify / safe partial / error]
    CHECK -->|Yes| BIND[Bind exact ranked product IDs and SKU]
    BIND --> STOCK[FictionStore.inventory per product, optional warehouse ID]
    STOCK --> VERIFY[Check identity, source version, stock arithmetic and limitations]
    VERIFY --> OUT[Authoritative findings + evidence refs + limits]
    OUT --> UI[Chat plus observed real execution events]
~~~

**Critical task dependency:** Inventory tasks receive their \`product_id\` **only from a validated \`top_sellers()\` result** (or a previously committed, verified result in the same session for follow-ups), never from an LLM's guessed top SKU. A model may propose the registered plan but cannot generate SQL, reorder the ranking, change the period, assert freshness, create stock evidence or certify a review decision. Use a fixed bounded dependency DAG, **not** an adaptive agent loop.

**Execution:** \`resolve → plan once → validate → sales read → validate/bind IDs → bounded inventory reads → verify → one final answer\`. No direct \`/ask\` Fiction path exists on the M0 baseline; this is target behavior. Preserve the existing \`AnswerResult\` / SSE contract: observed execution events, one authoritative verified final \`result\`, no unverified factual answer tokens or fabricated graph handoff. One rank query and at most **5** per-product inventory queries for the initial UC-03 slice (even though the underlying \`top_sellers\` method supports 1–20); bound returned records and trace payloads.

## 3. Data, calculation and evidence contracts

| Subject | Reuse / authoritative semantics | Must not infer |
|---|---|---|
| Ranked sales | \`FictionStore.top_sellers(month, limit)\`; join \`orders → order_items → products\` on canonical IDs. \`SUM(order_items.quantity)\` over \`orders.order_status='delivered'\` and **order_date** in calendar \`[YYYY-MM-01, next-month-01)\` | Not shipments delivered **during** that month, payment-settled units, revenue or returns-adjusted net sales |
| Rank / identity | Descending \`delivered_units\`, tie-break \`product_id ASC\`; each row has \`product_id\`, unique \`FR-\` SKU, \`delivered_units\`, \`contributing_order_lines\` | Never join on product display name or rank position alone; no rank drawn from another period/cohort |
| Inventory | \`FictionStore.inventory(product_id, warehouse_id?)\`: \`quantity_on_hand\`, \`reserved_quantity\`, \`available_snapshot = on_hand - reserved\`, \`warehouse_id\`, \`inventory_id\` | Base \`inventory\` has **no observation timestamp**. \`last_restocked_date\` is **not** freshness, and neither manifest \`dataset_business_as_of\` nor request time establishes stock freshness |
| Missing warehouse/stock | Report each **recorded** row with \`inventory/<id>\`; absence of rows is \`NO_INVENTORY_RECORDS\` / unknown for that scope | Missing is not zero stock; listing recorded warehouses does not prove exhaustive enterprise coverage |
| Release / provenance | \`FictionStore.open(explicit_db, manifest)\`, one immutable verified release; identical \`source.version\` and \`source.sha256\` across both calls; \`record_refs\`, \`scope\`, \`temporal\`, \`limitations\` | No legacy \`EL-###\`, VND/completed-order semantics, mutable/cloud/live source fallback |

**Period correctness:** Sales months are calendar months, **not** the \`sales_targets.month='2026-10'\` cohort window (\`2026-10-04..2026-11-03\`). The same label must not silently select different intervals. \`top_sellers()\` marks a first/last/partially observed or future month with \`PARTIAL_OR_FUTURE_PERIOD\`; preserve that limitation. If the operator says “tháng trước”, resolve relative to the pinned Fiction business reference **2026-11-03, Asia/Ho_Chi_Minh**, expose the resolved calendar interval and reject unsupported ambiguity. No default month if neither request nor committed context supplies one.

**Temporal non-equivalence:** A historical October sales ranking and untimed inventory records can be **displayed side by side** but **cannot be time-aligned**. Do not calculate a “stockout”, shortage probability, cover days, reorder quantity or “demand exceeds supply” conclusion from their ratio. Requests for “còn hàng ngay bây giờ?”, “tồn cuối tháng 10?” or live service levels must return \`INSUFFICIENT_EVIDENCE\` for the time-qualified claim while showing only independently supported historical/undated facts.

**Ranking evidence:** \`top_sellers()\` returns an \`aggregate_evidence\` descriptor (source tables/joins/filter/measure/period/contributor count); \`products/<id>\` is **identity evidence only**, never proof of sold units. The verifier must require a compatible aggregate definition and independently compare ranked quantities/counts/ordering to read-only SQL on the pinned release. Per-inventory-row refs prove only those recorded quantities. Never invent order-line refs for an aggregate.

**Warehouse scope:** An optional \`warehouse_id\` filters **inventory only**; current \`top_sellers()\` is a company-wide ranking and cannot be called “top seller in warehouse X”. A named warehouse must first resolve unambiguously to a trusted canonical warehouse UUID or be clarified; never pass names as IDs. Requested channel/store-specific sales ranking is unsupported by this initial capability and must not be quietly dropped.

**Identity and source gate:** Every inventory row must match the bound ranked \`product_id\` and requested \`warehouse_id\` (if any), and have unique row identity, integer \`on_hand >= reserved >= 0\`; returned \`scope.product_id\` and source hash must agree with Sales. Block a mixed-source/cross-product joined claim; return safe partial facts only if their own provenance is valid. Reject guessed/model-altered product IDs and unauthorized scope expansion.

**Screening, not stock decision:** Show ranked delivered units next to warehouse recorded on-hand/reserved/available. Optionally label **\`RECORDED_ZERO_AVAILABLE\`** only when an actual returned row has zero recorded available; **\`MISSING_INVENTORY_EVIDENCE\`** when the requested scope returns no row. These are evidence-review prompts, **not** proof of present stockout or a deterministic purchase/transfer recommendation. Do not introduce arbitrary low-stock thresholds in UC-03.

**Result contract:** Reuse existing \`answer\`, \`records\`, \`contexts\`, \`request_id\` and shared #28/#30 evidence/limitation fields, not a second API schema. Each result includes explicit \`sales_period_start/end_exclusive\`, \`sales_status_filter\`, \`rank\`, \`product_id\`, \`sku\`, \`delivered_units\`, \`contributing_order_lines\`, bounded warehouse inventory rows, aggregate/source refs, limitations and observed execution/trace metadata. Keep execution state, per-finding evidence fitness and disposition separate:

| Condition | Allowed conclusion |
|---|---|
| Trusted monthly aggregate + matching recorded inventory rows | \`SUPPORTED\` **for scoped historical sales and undated stock figures only**; inventory freshness remains unverified |
| Zero recorded available on a returned row | \`NEEDS_REVIEW\` **only for a proposed manual stock-verification follow-up**; no current-stockout or replenishment verdict |
| Missing inventory row, partial-month data or time-qualified stock request | \`INSUFFICIENT_EVIDENCE\` **for the affected claim**; preserve separately verified ranks/facts when appropriate |
| Invalid plan/identity/release, malformed stock, timed-out tool | Clarify, deny or fail safely; no joined result, no invented data, no committed unverified answer |

## 4. Source-to-code ownership (reuse first)

| Responsibility | Existing code / owner | Minimum UC-03 integration |
|---|---|---|
| Release-bound SQL | \`retailiq/domain/fiction.py\`: \`FictionStore.open\`, \`top_sellers\`, \`inventory\`; \`retailiq/infrastructure/sqlite.py\` | Reuse first; targeted domain validation/mapping only if a test demonstrates a gap; preserve original method meanings |
| Session / context | \`retailiq/api/http.py\`, \`retailiq/infrastructure/sessions.py\`, [#22](https://github.com/hungtvb/retailIQ/issues/22) | Commit ranked \`product_id\`, \`sku\`, month, rank and source version as verified references; follow-ups resolve same session only |
| Planning / agent execution | \`retailiq/orchestration/week1_graph.py\`, existing specialist/tool infrastructure, [#23](https://github.com/hungtvb/retailIQ/issues/23) | Two registered capabilities with validated dependent input binding and bounded fan-out, no additional Agent stack |
| Evidence / transport / UI | Existing verifier, \`retailiq/observability.py\`, \`frontend/src/main.tsx\` / \`frontend/src/graph.ts\`, [#21](https://github.com/hungtvb/retailIQ/issues/21), [#28](https://github.com/hungtvb/retailIQ/issues/28), [#30](https://github.com/hungtvb/retailIQ/issues/30) | Verify aggregate + row provenance, display separate time scopes and actual executed directed edges |
| MCP / RAG | Shared [#26](https://github.com/hungtvb/retailIQ/issues/26) / [#27](https://github.com/hungtvb/retailIQ/issues/27) | **Not required** to demonstrate this SQL-only cross-source UC; consume only an already-reviewed shared boundary when justified |

UC-03 has **no dependency on UC-01's case policies** or UC-02's monetary rules. It **does** depend on the shared Fiction read contract plus orchestration/context/evidence/UI integration. Do not duplicate their ownership or claim they are complete because the UC-03 design exists.

## 5. Acceptance scenarios — design only, NOT RUN

**Golden SQL cases:** Execute against the **real, pinned** \`fiction_retail.sqlite\`, choose exact product IDs/values from an independently written SQLite oracle (not from \`FictionStore.top_sellers()\` itself), and record the expected observations at test time. No release top-SKU/stock quantity is asserted here without reading that DB.

| ID / request | Independent expected checks |
|---|---|
| **UC03-G1 — October top 5** | For \`month='2026-10'\`, \`limit=5\`, independently compute delivered-order \`SUM(quantity)\`, \`COUNT(order_item_id)\`, descending units / ascending \`product_id\`; verify exact product UUID, SKU, rank, counts, calendar half-open period, aggregate descriptor, source SHA; exclude cancelled/non-delivered orders |
| **UC03-G2 — Top 1 inventory across recorded warehouses** | Select G1's **actual** first \`product_id\` (not a hardcoded guessed SKU); independently fetch inventory rows for that ID, check warehouse IDs, \`on_hand - reserved\`, \`inventory_id\`, missing/undated notice and matching release |
| **UC03-G3 — One warehouse** | Use an existing canonical warehouse UUID from G2; rank must remain **company-wide** while inventory filters to that warehouse. If no matching row, return missing evidence, not zero |
| **UC03-G4 — Partial month / period scope** | Request \`2026-11\` (partial at pinned as-of) and \`2026-10\` calendar month separately; preserve \`PARTIAL_OR_FUTURE_PERIOD\` appropriately; never substitute sales-target cohort \`2026-10-04..2026-11-03\` |
| **UC03-F1 — Identity / dependency tamper** | LLM plan injects a different SKU, wrong \`product_id\`, unauthorized warehouse, rank from a second month, duplicated inventory row or mismatched source SHA → block joined answer; no silent broadened query |
| **UC03-F2 — Missing / corrupt facts** | No inventory record, no ranked rows, ambiguous warehouse, non-integer/negative stock, reserved > on-hand, malformed month/UUID, \`limit > 5\`, missing/replaced DB → accurate missing/error state, no zero-from-absence or legacy fallback |
| **UC03-F3 — Ranking and temporal edges** | Tie on delivered units uses \`product_id ASC\`; cancelled order excluded; same SKU represented once; warehouse zero is qualified; “live stock”, month-end stock, days-of-cover and warehouse-specific sales rank are not asserted |
| **UC03-F4 — Session / tools / transport** | Same-session “top 1 đó ở kho nào?” preserves verified month/product ID; new session or uncommitted rank asks clarification; bounded calls, timeout/disconnect safe, no unverified answer persisted, no source DB writes |

**Future actual Chat/Agent/Graph acceptance (not M0):**

1. New session: “Top 5 sản phẩm theo số lượng của đơn \`delivered\` trong tháng 10/2026, kèm tồn kho được ghi nhận theo kho.” Confirm G1/G2 via **real** \`/ask\` and tool inputs/results; one sales read followed by bounded inventory reads for exact ranked IDs.
2. Same session: “Sản phẩm đứng đầu hiện còn hàng ở kho nào?” Correctly bind G1's first UUID; show recorded rows and explain that **current** stock is unverified.
3. Same session: “Thế tồn kho cuối tháng 10 có đủ cho nhu cầu không?” Decline the time-qualified sufficiency/coverage claim; do not convert undated stock and past delivered units into a forecast.
4. New session: “Còn top 1 đó?” Ask which month/product; do not import identity across sessions.
5. Inspect observed LangGraph/tool invocation IDs, arguments, request/result edges and shared SSE final result in browser/trace. A fluent LLM response, static graph or fixture-only test is **not** a PASS.

**Evidence modes must be separated:** deterministic fixture tests; real local pinned SQLite + independent SQL oracle; provider-backed chat/tool execution; browser/actual trace (and actual MCP only if used). At code acceptance record commit/design SHA, Fiction manifest/db SHA, exact queries and source IDs, mode/provider/model, expected vs observed ranks/stock, tool-call IDs, request/trace IDs, no-write check, and remaining gaps. Do not mark UC-03 E2E accepted until each claimed layer is observed.

## 6. Implementation order / stop gate

1. **M1 — SQL + verifier:** Reuse the M0 \`top_sellers\` and \`inventory\` contracts; add only thin joined-evidence validation and ranked binding. Run G1–G4 + F1–F3 against a pinned real DB/oracle and focused corrupt-source fixtures.
2. **M2 — Controlled dependent execution:** After the reviewed shared #22/#23/#28 contract is available, wire **one** top-1/top-5 request with exact Sales→Inventory binding through existing \`/ask\`; inspect actual tool calls and no-write behavior. Do not pre-empt UC-01/UC-02 delivery.
3. **M3 — Follow-up and UI/E2E:** Add committed-session rank references, verified-first final response, actual observed graph/SSE and F4/provider-backed scenarios. Reuse shared #21/#30 UI mechanisms.
4. **Optional later:** Warehouse-specific sales attribution, verified timestamped inventory, new analytics heuristics or RAG context require **their own source/data contract and evidence**, not an unreviewed extension of this UC.

**Stop condition:** If Fiction cannot establish observation time, warehouse sales attribution, or quantity-at-historical-date, surface the limitation and stop. **This documentation PR changes no feature code and does not run application CI solely for Markdown.**
