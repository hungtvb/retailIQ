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

## UX

Desktop: compact product header; collapsible conversation sidebar; flexible chat column; execution matrix pane showing request status and event-grounded node relationships. No duplicated execution timeline or inspector. On mobile, chat comes first; the matrix follows.

Visual identity: off-white canvas, crisp typography, low-contrast boundaries, graphite labels and teal primary action. Color on graph indicates role (agent violet, tool blue, validation amber, output teal) plus explicit state labels. Subtle animation only for active execution; honor `prefers-reduced-motion`.

## Validation acceptance

1. Build + TS typecheck.
2. Session new/switch/delete, SSE streamed answer and evidence, no fake historical trace.
3. Matrix nodes and edge states only from emitted events; no invented MCP/subagent connections.
4. Desktop/mobile screenshots with no page overflow, working chat input.
5. Existing Python business/scenario audits remain green.

## Run

```bash
cd frontend && npm install && npm run build && cd ..
python -m uvicorn retailiq.api:app --host 127.0.0.1 --port 8000
```

Open `http://127.0.0.1:8000/workspace`. For development: run Vite in `frontend` with `npm run dev`; it proxies `/api` and `/ask` to localhost port 8000.

## Next work, not claimed complete

Persist event traces per request; support selecting an answer to replay its real trace; richer skill/MCP metadata; accessible graph summaries; authenticated roles and hardened deployment. These need separate scoped design and testing.
