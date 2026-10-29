# RetailIQ Product Workspace — first vertical slice

## Goal

Build an analytics tool, not a presentation site. Primary experience: manage conversations, ask retail questions, view answer/evidence, watch factual agent execution events in a **non-interactive dynamic 2D matrix**.

This work starts on branch `feature/product-workspace-v1`, based on `feature/four-week-graph-workflows`. It does not modify `main`.

## Decisions

- **Frontend:** React + TypeScript + Vite. A clean design system in `frontend/src/styles.css`, not additional overrides on legacy CSS.
- **Backend reuse:** FastAPI API, session persistence, streaming and observability remain the source of truth. A new `/workspace` route serves the built SPA. Legacy `/` is unchanged until replacement is validated.
- **Rendering:** SVG-based dynamic network matrix. No graph interaction, physics layout, new orchestration backend or graph framework.
- **Truthful evidence:** Only observed SSE events create active agent/tool/skill/handoff nodes. A selected skill is labeled *selected*, not *executed*. No MCP/subagent node unless a real matching event arrives. A persisted answer does not imply its live trace is available after reload.
- **Safety:** Only show allowlisted event metadata. UI uses React text rendering; do not inject model HTML. Existing application is local-only and unauthenticated.
- **Initial state:** Empty conversations show an empty graph, not a fabricated example execution.
- **Trace durability (v1.1):** Streamed requests save up to 160 allowlisted metadata events per successful assistant turn, keyed by its `request_id` and session. Saved traces reload through `GET /api/sessions/{id}/traces/{request_id}`. Missing legacy traces remain visibly unavailable; truncated traces are labeled partial. Deleting a session cascades to its traces.
- **Execution attribution:** A handoff is not proof that the source agent completed. Response links are created only when `chat.turn_result` identifies the responsible agent. Display-only connections never imply an unobserved MCP/skill call.
- **Layout:** Stable multi-row placement without collisions; small screens use a legible zigzag/stack rather than shrinking an 800px diagram. Dense desktop graphs can scroll within the visualization.

## UX

Desktop: compact product header; collapsible conversation sidebar; flexible chat column; execution matrix pane showing request status and event-grounded node relationships. No duplicated execution timeline or inspector. On mobile, chat comes first; the matrix follows.

Visual identity: off-white canvas, crisp typography, low-contrast boundaries, graphite labels and teal primary action. Color on graph indicates role (agent violet, tool blue, validation amber, output teal) plus explicit state labels. Subtle animation only for active execution; honor `prefers-reduced-motion`.

## Validation acceptance

1. Build + TS typecheck.
2. Session new/switch/delete, SSE streamed answer and evidence, request-scoped trace selection (no authentication yet) and exact saved trace replay.
3. Matrix nodes and edge states only from emitted events; no invented MCP/subagent connections or completion states.
4. Desktop/mobile/handoff screenshots, collision detection and final-result provenance checks on actual Chromium geometry.
5. Existing Python business/scenario audits remain green.

## Run

```bash
cd frontend && npm install && npm run build && cd ..
python -m uvicorn retailiq.api:app --host 127.0.0.1 --port 8000
```

Open `http://127.0.0.1:8000/workspace`. For development: run Vite in `frontend` with `npm run dev`; it proxies `/api` and `/ask` to localhost port 8000.

## Next work, not claimed complete

- Full tracing for non-streamed POST requests (streamed conversations only in v1.1).
- Graph-side presentation of causal MCP/resource/skill relations based on newly instrumented real events; current test contracts are synthetic and do **not** establish that every runtime can emit those events.
- User authentication, access control, multi-worker synchronization, larger graphs and deployment hardening. A local-only app is not production-ready.
