# RetailIQ — Four-Week Graph Workflow Demo

> Scope: **local synthetic teaching demo**, not a production Retail OS. Code and tests are on
> `feature/four-week-graph-workflows`. This document separates completed local slices,
> optional integrations, and still-unverified course requirements.

## Why this shape?

Business objective remains **Faster · Easier · Reliable** access to retail information.
We reuse the existing FastAPI, SQLite, LangGraph Week 1 chat, product RAG, SSE,
sessions, logs and ROI rather than introducing a new frontend framework, external
orchestrator, broker, cloud deployment or real order payment system.

The **Workflow Graph** tab presents actual backend-recorded nodes and directed,
business-labelled handoff edges. The workflow replay is intentionally **not**
mislabelled as real-time LangGraph streaming. The Assistant's execution graph
is driven by the existing **live SSE log events**.

## Four-week capability map

| Week | Demonstrated in this branch | Important caveats |
|---|---|---|
| 1 | Existing SQL/RAG chat, LangGraph full-mode path, session memory, SSE events; assistant trace is now a node/edge graph | Offline path remains deterministic. LangSmith/RAGAS claims require separate live evidence. |
| 2 | Canonical KPI definitions; 4 freshness target tiers; timestamp-based stock freshness check; optional read-only MCP Inventory + Order tools, LangChain MCP adapter; existing short-term chat context | Normal demo uses local MCP-equivalent adapter and explicitly says transport was not exercised. Enable `RETAILIQ_WORKFLOW_USE_MCP=1` with MCP deps for actual stdio; separately verify that route. No long-term customer profile or measured hybrid-reranker quality in this branch. |
| 3 | Simulated location row scope; read-only KPI alert screening; pricing proposal verified and paused for manager decision; existing cost/ROI page | Role selector is not authentication or real RBAC. Decisions only update a local workflow status. Langfuse/DeepEval live integrations and security certification are not claimed. |
| 4 | Five specialist *roles* in an A2A-style step chain; single-location allocation, customer guest context, read-only list pricing, order draft, verification, manager gate, report | These are deterministic specialist steps, not five independently deployed LLM agents or the interoperable A2A protocol. No order, reservation, payment or price mutation. |

Do not mark all Weeks 1–4 course gates PASS based on this simulation. Real
provider integrations, independent agent behavior, RAG/retrieval evaluation
and external observability require separate tests/evidence.

## Graph semantics

Each scenario is described by a server-provided JSON graph:

- `nodes[]`: stable IDs, label and type (input/agent/tool/guard/human/output).
- `edges[]`: source, destination and a short interaction label.
- `events[]`: steps **actually executed** on the server; every event includes a
  node, status, detail and previous-node reference.
- `status`: completed / blocked / pending_manager / approved_simulated / rejected.

The renderer creates accessible focusable DOM nodes and SVG paths with arrowheads,
no external graph dependency. **Overview** shows phase lanes and executed handoffs;
**Tools & sources** adds Step → Tool/Operation → Data Source reference chains.
The **Node inspector** distinguishes recorded event evidence from implementation
metadata; the **Execution timeline** supports node selection and replay.
Backend details are inserted via `textContent`, not via `innerHTML`.

**Chat graph:** live logs can be emitted by offline reviewed SQL or by full-mode
LangGraph. Only observed tool steps appear as completed evidence.

**Workflow tab:** requests return a persisted trace shown immediately;
**Replay steps** animates it on request. A node is not marked complete unless
present in the trace. `graph.lineage` is a source/operation reference, **not
additional observed agent tool calls**. Week 3/4 specialists consume preflight
SQLite data and deterministic calculations.
A blocked verification never emits an approval event; on review, the persisted
decision appends manager and finalize events with their handoff.

## Setup

```bash
python -m pip install -r requirements-offline.txt
python -m scripts.seed
python -m uvicorn retailiq.api.http:app --host 127.0.0.1 --port 8000
```

Open `http://127.0.0.1:8000` and select **Workflow Graph**.

For optional **actual MCP stdio transport** (not installed by the offline
dependency group):

```bash
python -m pip install -r requirements-mcp.txt
RETAILIQ_WORKFLOW_USE_MCP=1 python -m uvicorn retailiq.api.http:app --host 127.0.0.1 --port 8000
```

You can also inspect `python -m retailiq.mcp_server` using an MCP stdio client.
MCP only exposes read-only synthetic inventory/order data. If it fails,
the API returns an error rather than silently claiming a successful MCP call.

## API contracts

```http
GET /api/workflows/definitions
GET /api/workflows/semantics
POST /api/workflows/run
Content-Type: application/json

{"scenario":"week4","sku":"EL-003","quantity":2,"role":"analyst"}
```

Other scenarios: `week1`, `week2`, `week3`, `alerts`. The response includes
`id`, `status`, `events`, `graph`, `report`, `simulation_notice`.

```http
GET /api/workflows/runs/{id}
POST /api/workflows/runs/{id}/review
Content-Type: application/json

{"role":"manager","decision":"approve"}
```

Only a run in `pending_manager` may be decided, once. The `manager`
field is self-declared and therefore **not a security control**. Real deployment
would require authenticated identity, enforced authorization, audit retention,
transactional business-action constraints and a genuine approval backend.

## Demo walkthrough

1. Ask **Which products are top sellers?** in Assistant; observe live router,
   agent and tool nodes and the returning evidence/answer.
2. Open Workflow Graph, select **Week 2**, SKU `EL-003`, Run. Read timestamp
   evidence; note that 15-minute freshness is NOT met by old seed snapshots.
3. Select **Week 3**. Run with analyst scope and inspect the pricing proposal.
   Try Approve as analyst (denied), switch to manager and Approve (recorded
   simulation only). No product price is changed.
4. Select **Week 4**. Run quantity `2`, inspect the five specialists and
   verification edge. Approve/reject as manager; no sales order is inserted.
   For a blocked case use a test fixture with each location's availability
   below the requested quantity.
5. Select **Week 3 alerts** and inspect the threshold rule. Cost & ROI and
   Execution Logs remain separate views.

## Acceptance and evidence

```bash
python -m pytest -q tests/test_four_week_workflows.py
node --check web/assets/workflow-graph.js
node --check web/assets/workflow-ui.js
node --test tests/frontend_format.test.cjs
node --test tests/workflow_ui_journey.test.cjs
```

Key regression conditions: graph edges point to known nodes, timestamp freshness
does not falsely say live, simulated role denial, at-most-once manager decision,
price/order non-mutation, insufficient stock blocks approval, five specialist
handoffs, MCP opt-in path is called only when enabled, and no unsafe HTML
injection in new graph rendering.

**Evidence scope:** pytest runs offline with a mock MCP adapter when testing
the optional route; they do not prove a live stdio MCP server handshake,
live LLM, Langfuse, DeepEval, hybrid reranker quality, or autonomous A2A protocol.
Capture those separately if course grading requires them.

## Real browser E2E acceptance (not a unit test)

GitHub Actions starts the actual FastAPI app and seeded SQLite, opens it in
headless Chromium, navigates all five scenarios across Weeks 1–4, checks
tool/source provenance, recorded states, replay, approval and rejection.
The Week 4 screenshot is stored in the Actions artifact named
`retailiq-week4-browser-screenshot`.

To run locally with Chrome/Chromium already installed:

`python -m pip install playwright`
`python -m scripts.smoke_workflow_browser`

This confirms the offline synthetic user journey in a real browser. It does
not establish live LLM calls, autonomous A2A, real MCP transport or
authenticated manager approval. A green pytest suite alone is not UI acceptance.
