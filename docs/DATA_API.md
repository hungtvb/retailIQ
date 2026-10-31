# RetailIQ — Data & API Contracts

**Status:** implementation-aligned local contract, audited 2026-10-31 against `scripts/seed.py`, `retailiq/domain/`, `retailiq/infrastructure/` and `retailiq/api/`. This documents **existing behavior**, not a production integration specification or evidence that every capability has passed testing.

**Ownership:** this file defines data fields, KPI semantics, API shapes and limitations. [Architecture](ARCHITECTURE.md) explains component boundaries; [Design](DESIGN.md) explains request flows; [Testing & Scenarios](27_BEHAVIORAL_ACCEPTANCE_MATRIX.md) specifies oracles; [Capability Ledger](29_COURSE_CAPABILITY_ACCEPTANCE_LEDGER.md) owns acceptance status. Do not duplicate implementation status here.

## 1. Data authority and storage

RetailIQ uses **synthetic** local data rather than live POS/OMS, ERP/WMS or PIM connections. These real-world systems are *conceptual ownership*, not deployed integrations.

| Logical business authority | Current implementation | Contract |
|---|---|---|
| POS / OMS sales | `orders`, `order_lines` in retail SQLite | Completed-order quantities, revenue and ranking; line prices and discounts are transactional facts |
| ERP / WMS stock | `inventory`, `locations` in retail SQLite | SKU/location on-hand, reserved, available and row snapshot timestamp |
| Product master | `products` in retail SQLite | Stable SKU, catalog list price, name, category and catalog-added date |
| Product knowledge | Local product/knowledge files; optional Chroma index | Source-addressable specifications. **Not** live stock, authoritative sales or current retailer policies |

| Local store | Default / override | Lifecycle and limitation |
|---|---|---|
| Retail fixture | `data/retailiq.sqlite3` / `RETAILIQ_DATA_DB` (query adapter) | `python -m scripts.seed` recreates the **default** retail fixture. Back up custom data before re-seeding; `scripts.seed` is not a safe incremental migration. |
| Session/history | `data/chat_sessions.sqlite3` / `RETAILIQ_CHAT_DB` | Local SQLite conversation messages, consented session-only preferences and bounded execution traces; no authenticated user ownership |
| Workflow scenarios | `data/workflow_demo.sqlite3` / `RETAILIQ_WORKFLOW_DB` | Deterministic run events and simulated approval decisions, **not** operational order/price writes |
| Graph checkpointer | `data/agent_checkpoints.sqlite3` / `RETAILIQ_CHECKPOINT_DB` | Local full-mode LangGraph session checkpoints; not a distributed persistence service |
| Product documents and index | `data/product_docs/`, `data/knowledge/` and configured RAG index | Re-index using `python -m scripts.index_products`; offline lexical search is not vector retrieval |
| Local diagnostics | `data/logs/retailiq.jsonl` / `RETAILIQ_LOG_FILE` | Rotating JSONL telemetry, **not** an immutable compliance audit or remote LangSmith traces |

The API is loopback-only by middleware checks of peer and Host. This is **not identity authentication, RBAC, a tenant boundary or production security**. Retail analytics use read-only parameterized queries via `retailiq/infrastructure/sqlite.py`; no unrestricted LLM-generated SQL is executed.

## 2. Data model

The relationships below are **logical**. The seed schema defines keys and an inventory CHECK, but does not declare every drawn foreign-key relation. Chat and workflow tables live in **separate databases**.

~~~mermaid
erDiagram
    PRODUCTS ||--o{ INVENTORY : stocked
    LOCATIONS ||--o{ INVENTORY : holds
    PRODUCTS ||--o{ ORDER_LINES : sold_as
    ORDERS ||--o{ ORDER_LINES : contains
    SESSIONS ||--o{ MESSAGES : contains
    SESSIONS ||--o{ EXECUTION_TRACES : records
    SESSIONS ||--o| CUSTOMER_SESSION_MEMORY : optionally_stores
~~~

### Retail fixture (`scripts/seed.py`)

| Table | Key fields | Meaning / invariants |
|---|---|---|
| `products` | `sku` PK, `name`, `category`, `price_vnd`, `spec`, `catalog_added_at` | Synthetic list price in **integer VND**; `catalog_added_at` is catalog insertion date, **not** product release or source refresh |
| `locations` | `id` PK, `name`, `channel` | Synthetic store/warehouse locations |
| `inventory` | (`sku`, `location_id`) composite PK, `on_hand`, `reserved`, `updated_at` | Seed CHECK: `on_hand >= reserved >= 0`; runtime requires integer quantities, correct SKU/location, timezone-aware valid timestamp |
| `orders` | `id` PK, `ordered_at`, `channel`, `status` | `ordered_at` is transaction date, **not** the source-refresh timestamp |
| `order_lines` | `id` PK, `order_id`, `sku`, `quantity`, `unit_price_vnd`, `discount_vnd` | `discount_vnd` applies to the **entire line**, not per unit; completed sales reject invalid quantities/prices/discounts |

Seed fixture: 10 catalog SKUs, three locations and 120 generated orders. This is fixed synthetic coverage, not a store-data volume or quality claim. Not every business invariant is a SQL table constraint; `domain/analytics.py` validates source data before calculations and fails on inconsistency.

### Conversation / workflow persistence

| Table | Key fields | Contract |
|---|---|---|
| `sessions` | `id` UUID text PK, `title`, `active_agent`, `created_at`, `updated_at` | Local sessions, not authenticated customers |
| `messages` | `id` PK, `session_id` FK, `role`, `content`, `intent`, `agent`, `evidence_json`, `request_id`, `created_at` | Stored after successful turn; bounded evidence metadata is not authoritative inventory/sales data; `request_id` added via compatibility migration |
| `execution_traces` | (`session_id`, `request_id`) PK, `events_json`, `truncated`, `created_at` | Allowlisted, bounded event metadata for recorded assistant turns only; no raw prompts, tool outputs or stack traces |
| `customer_session_memory` | `session_id` PK/FK, `preferences_json`, `consented_at`, `updated_at` | Explicit opt-in preferences, limited to that same session; delete session cascades to preferences |
| `workflow_runs` | `id` PK, `scenario`, `status`, `trace_json`, `report`, `created_at`, `decision_at` | Stored in workflow SQLite only. A recorded approval is simulated, not an authorized external write |

The sessions API returns **at most 200 newest messages** in display order and flags `messages_truncated`; older rows can still exist. A saved `execution_traces` record may be absent for a legacy or non-streamed turn; absence is not proof of an empty execution. The preference store accepts only validated attributes and requires explicit consent.

## 3. Canonical KPIs and time semantics

**Business source of truth:** `retailiq/domain/analytics.py` (calculations and validation); `domain/semantic.py` (named metric definitions, freshness *targets*). All monetary results are integer **VND**, not float currency estimates.

| Metric | Definition used by current SQL | Exclusions / guardrails |
|---|---|---|
| Available stock | Per SKU/location: `available = on_hand - reserved`; aggregate is the sum across included locations | Missing stock rows are **not** zero; duplicate/mismatched location, negative inventory or invalid timezone fails. Does **not** imply freshness. |
| Net revenue | `SUM(quantity * unit_price_vnd - discount_vnd)` for **completed** orders in requested calendar month, grouped by channel; optional verified SKU/channel scope | Cancelled/out-of-period orders excluded; before returns, with no separate taxes or shipping represented in fixture. Do **not** replace a product-scoped answer with store-wide revenue. |
| Top sellers | Completed-order `SUM(quantity)` by SKU/month, descending units, then SKU ascending | `domain.analytics.top()` returns **at most five** ranked SKUs, and callers may display a subset; not ranked by net revenue or margin. |
| Catalog price extremes | Read `products.price_vnd` sorted ASC/DESC, stable SKU tie-break; optionally allowed category | List price only, **not** realized order price or discount-policy recommendation |
| Product knowledge | Local parsed/cited document facts, optionally retrieved by Chroma embeddings/hybrid search | Not stock truth, not independently verified warranty, not proof that source is up to date |
| Order state | Recorded `orders.status` through read-only local MCP order lookup | Order `ordered_at` is not a data-refresh timestamp; no write/status transition |

**Reporting period:** `RETAILIQ_AS_OF` sets the reproducible synthetic reference date (default `2026-10-28`). `month()` returns `YYYY-MM`; explicit months/years or “last month” resolve according to `domain.analytics.requested_month()`. A month without a year uses the reference year. SQL uses a half-open calendar-month interval [start, next-month-start). The chat response `as_of` denotes reporting **month**, not live stock time. Inventory has a distinct per-row `updated_at`.

**Data integrity:** completed-order lines must have an existing product, positive integer quantity, nonnegative integer unit price and line discount between zero and line value. Revenue and top seller code validates this before aggregating. SKU values are validated and normalized; ambiguous user references must be clarified, not silently broadened.

## 4. Freshness policy versus observed freshness

`domain/semantic.py` defines *targets*, not real-world SLAs:

| Metric | Nominal tier | Target | Evidence limitation |
|---|---|---|---|
| `available_stock` | `15_min` | 900 s | Inventory rows have `updated_at`; compare the **oldest** included location timestamp to the target |
| `net_revenue` | `hourly` | 3,600 s | Synthetic orders have no trustworthy source-refresh timestamp |
| `top_sellers` | `daily` | 86,400 s | Same source-refresh gap |
| `product_knowledge` | `daily` | 86,400 s | Catalog/index time is not external document freshness |
| `order_state` | `live` | 0 s | Local snapshot cannot establish live consistency |

`POST /api/workflows/freshness/route` may return `PASS` for **local timestamp-versus-target evaluation**, `STALE` for an out-of-window/future snapshot or `UNVERIFIED` when no reliable timestamp exists (including requests for live consistency). `guaranteed` remains `false`. A stricter requested tier overrides baseline; a looser tier cannot relax it. Source selection alone does not execute the tool. The API can optionally re-read inventory through actual **local stdio MCP** (`RETAILIQ_WORKFLOW_USE_MCP=1`) and compare it to reviewed SQL before returning; it is not a hosted MCP service or live retailer API.

## 5. HTTP API (as implemented)

Inspect `GET /openapi.json` from the running FastAPI app for precise runtime schema and Pydantic field validation. `retailiq/api/http.py` owns app entrypoint and localhost middleware; other routers live in `retailiq/api/`. HTTP errors generally use `{"detail": ...}`, but **SSE failures use event payloads**.

### Chat and interface

| Method / path | Input | Success / meaningful errors |
|---|---|---|
| `GET /health` | — | `{"status":"ok"}` (process only; no provider readiness) |
| `GET /`, `GET /workspace` | — | Legacy UI and built Workspace UI; unbuilt Workspace returns `503` |
| `POST /ask` | `{"question":"...", "session_id":null}` | Question 3–500 chars; optional session ID 36 chars. `200` includes `question`, `intent`, `mode`, `as_of`, `answer`, `records`, `contexts`, `active_agent`, `handoff`, `subagents`, `skill`, `session_id`, `request_id`; optional `route_fallback`, `query_plan`. Invalid `422`, missing session `404`, busy session `409`, execution/index/dependency failure `503`. |
| `POST /ask/stream` | Same `AskBody` | SSE over POST, `text/event-stream`; `started`, zero or more `log`, `result`, `done` or `error` then `done`. **Execution events, not model token streaming**. Missing session `404`; capacity limit (8 workers) `503` with `Retry-After`. |

`X-Request-ID` is attached by HTTP middleware. Responses may have empty records/contexts or null handoff. `mode` distinguishes offline deterministic fallback from full LangGraph/LLM execution; a response `active_agent` label alone does not prove a model tool call. Session-backed successful turns persist two messages; `request_id` correlates events where recorded.

### Sessions, consent and traces

| Method / path | Meaning / boundary |
|---|---|
| `POST /api/sessions` | Create a local session; optional `title` max 80; `201` |
| `GET /api/sessions` | List sessions (default 50, latest updated first); `200` |
| `GET /api/sessions/{session_id}` | Session plus bounded messages and `messages_truncated`; `404` unknown |
| `DELETE /api/sessions/{session_id}` | Delete graph checkpoints then session/messages and linked local memory; `204`; `404` unknown, `409` busy, `503` checkpoint cleanup failure |
| `GET /api/sessions/{session_id}/memory` | Return `{"consent":false,"preferences":{},"scope":"session_only"}` if unset; `404` unknown |
| `PUT /api/sessions/{session_id}/memory` | Explicit `{"consent":true,"preferences":{"preferred_category":"Accessory"}}` (validated fixed values); must have at least one allowed preference when opting in; `422` invalid, `409` busy |
| `DELETE /api/sessions/{session_id}/memory` | Revoke stored preferences; `204` |
| `GET /api/sessions/{session_id}/traces/{request_id}` | Recorded, allowlisted local execution event trace; `404` if session/trace absent (including older/non-streamed turns) |

All session/memory endpoints lack authenticated customer identity. An arbitrary session UUID is not proof that the caller owns a real customer's data.

### Freshness, semantic layer, workflow simulation

| Method / path | Request and actual behavior |
|---|---|
| `GET /api/workflows/semantics` | Return metric definitions and four freshness tier targets, with non-guarantee notice |
| `GET /api/workflows/definitions` | Return scenario graph *definitions* and lineage labels; no agent/tool execution |
| `POST /api/workflows/freshness/route` | `{"metric":"available_stock","sku":"EL-003","requested_tier":"15_min"}`. Metric is one of stock/revenue/top sellers/product knowledge/order state; tier optional. `sku` required **only** for inventory. Inventory performs read-only SQL (optional local MCP re-read) and evaluates row timestamps; other metrics return selected routes with `UNVERIFIED` timestamp status. |
| `POST /api/workflows/freshness/question` | `{"question":"Tồn kho của top seller ngay bây giờ?"}` (3–500 chars). Deterministically classify source needs; multiple sources return `REQUIRES_ORCHESTRATION` **without executing joined tools**; unrecognized intent `422`; stock without resolvable SKU `NEEDS_PRODUCT`. |
| `POST /api/workflows/run` | `{"scenario":"week4","sku":"EL-003","quantity":1,"role":"analyst"}`. Existing scenario IDs `week1`, `week2`, `week3`, `alerts`, `week4`; quantity 1–20. Executes **deterministic local scenario** and persists events/report; not the chat LangGraph or autonomous agents. |
| `GET /api/workflows/runs/{run_id}` | Return run status, events, graph definition, report and `simulation_notice`; `404` absent |
| `POST /api/workflows/runs/{run_id}/review` | `{"role":"manager","decision":"approve"}` or `reject`; records a **simulated** one-shot manager decision when pending. Caller-supplied role is **not authentication**. `403` wrong role, `404` missing, `409` not pending; no operational business write |

Scenario names retain historical course IDs for compatibility; they are not a recommendation to organize permanent source code by course weeks. A displayed graph node or simulated role does not prove independent agent invocation or A2A transport.

### Observability and cost estimate

| Method / path | Meaning |
|---|---|
| `GET /api/logs` | Read allowlisted local events; optional `limit` 1–200, `level` INFO/WARNING/ERROR/DEBUG, session and request filters. `source: local_rotating_jsonl`; `Cache-Control: no-store`; **not** remote trace or production audit. |
| `GET /api/roi/defaults` | Return editable assumptions, not observed costs |
| `POST /api/roi/estimate` | `ROIForm` workload, time, cost and token/rate estimates; result is illustrative and **not** verified time savings/ROI. Exact bounds in `retailiq/api/roi.py`. |

Non-loopback peer/Host requests to the app are rejected with `403`, including health, logs and workflows. Do not expose these unauthenticated local interfaces on a public network.

## 6. Local MCP contract (not HTTP routes)

`python -m retailiq.mcp_server` starts an optional **stdio** FastMCP server backed by synthetic read-only SQLite. Tool contracts in `retailiq/mcp_server.py`:

| MCP primitive | Input | Return / limitation |
|---|---|---|
| Tool `inventory_lookup` | `sku` | Per-location stock `records`, aggregate `available`, local snapshot source and freshness notice |
| Tool `order_lookup` | `order_id` formatted `ORD-0001` | Synthetic order and lines; unknown order returns null order/empty lines; never modifies status |
| Resource `retailiq://semantics` | — | Plain-text canonical semantic summary, plus reminder that observed timestamps are needed |

The LangChain MCP adapter is `retailiq/mcp_adapter.py`; it validates decoded tool results against inventory/SQL invariants. These are **local** MCP transport capabilities, not enterprise APIs, remote tools or proof of actual data freshness.

## 7. Contract change and verification rules

- **Schema:** compare changes against `scripts/seed.py`, `infrastructure/sessions.py`, `domain/workflow_demo.py`. Do not invent database-level foreign keys that are only logical relationships.
- **KPI:** update `domain.analytics.py` and `domain.semantic.py` together when meaning changes; test month boundaries, SKU/channel scope, invalid source data and negative cases with independent SQL/data oracles.
- **API:** verify router methods, request bounds, response fields and status/errors against `api/http.py`, `api/sessions.py`, `api/workflows.py`, `api/roi.py`, `api/logs.py`. Compare the generated OpenAPI contract when the app actually runs.
- **Freshness/access:** do not equate route selection, synthetic timestamp checks, localhost-only middleware or caller-provided role with live freshness, RBAC or authenticated authorization.
- **Evidence:** execution results live in dated CI artifacts/reports, not this contract. Record test SHA/mode/expected/observed and link them from the [capability ledger](29_COURSE_CAPABILITY_ACCEPTANCE_LEDGER.md). Keep generated reports and secrets outside Git.

**Documentation-only audit scope:** this description was checked against repository source. No live API request, provider test, production security assessment or business productivity benchmark is implied by the documentation update.
