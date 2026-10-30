# RetailIQ Week 1 — Conversational Analytics UI

## UX principle
This is an **operations workspace**, not a marketing landing page. The first screen should let retail managers **have a multi-turn conversation → examine the latest answer → inspect supporting data/sources and trace** without scrolling past promotional copy. It is a chat product grounded in business evidence, not an SQL query console.

## Current interface
- **Assistant**: persistent conversation thread, visible previous user/assistant messages, follow-up questions, compact composer and sample prompts. The latest answer appears once; earlier answers remain in the thread.
- **Answer**: latest assistant reply appears inside the conversation, with execution status in the chat heading; agent, reference period and full/offline indication appear in the adjacent evidence panel.
- **Data records**: evidence pane beside conversation renders `records` from the actual API as a semantic, non-sortable table (up to 200 visible rows; row count shown). CSV exports all returned records with spreadsheet formula injection protection.
- **Product sources**: unique filenames from retrieved contexts; plain text only (not invented clickable links).
- **Execution**: separate supporting SSE timeline below the data evidence; advanced metadata and raw JSON stay expandable.
- **Execution Logs**: compact filters and event rows backed by local JSONL.
- **Cost & ROI**: form, estimates, sensitivity and token-cost projection; figures remain illustrative.

## RetailIQ brand and mascot

- Logo: compact retail shelf + analytics + conversation icon in navy `#0b203b` and amber `#eea13a`. Wordmark retains the product name **RetailIQ Copilot**.
- **IQ** is the friendly robot mascot. The chat header and all restored AI replies use `/assets/brand/mascot-avatar.svg`; the new/empty conversation shows the compact guide illustration `/assets/brand/mascot-guide.svg`.
- An anonymous **U** avatar represents the user during the unauthenticated Week 1 local demo; it is not a user identity/profile photo.
- Brand files are locally served SVGs, without remote images/scripts; chat labels remain accessible text. Mascot is confined to chat and does not introduce a landing hero.
- Favicon: `/assets/brand/logo-mark.svg`. Structural coverage: `tests/test_chat_branding.py`.

## Brand refresh and per-agent identity (2026-10-28)

**Visual direction:** understated B2B analytics, not a cartoon-heavy landing page. Brand mark is a geometric navy box with a small amber verification accent; wordmark uses the existing RetailIQ name. The robot is reduced to a clean head-only treatment and appears only in the empty state. During conversation each agent is identified by a compact icon, human-readable label and understated color (color is never the sole indicator).

| Agent | Token | Hue |
|---|---|---|
| Supervisor | compass | Navy `#1c3656` |
| Sales | trending-up | Green `#126e50` |
| Inventory | package | Blue `#265dba` |
| Product | tag | Purple `#7046af` |
| IQ fallback | sparkles | Slate `#26415e` |

The single allowlisted mapper lives in `web/assets/agent-identity.js` and controls message labels, avatars, evidence badges and trace events. Unexpected agent names always fall back to IQ, never become arbitrary CSS class names.

## Rich response format (Week 1)

- **Markdown**: headings, bold/italic, lists, code spans, fenced code with copy, simple pipe tables, blockquotes and permitted `https/http` links.
- **Safe rendering**: `web/assets/response-format.js` creates DOM nodes and text nodes; it does **not** execute HTML from LLM output or allow JavaScript links. Markdown is supported on restored chat history and new answers.
- **Data-backed KPIs and charts**: Sales revenue (summed across actual SQL channel rows), stock available (summed across actual SQL location rows), top seller units (first ranked product). Mini bar charts only when numeric SQL rows exist, using the actual returned values. This is presentation logic, not a new tool or AI numerical inference.
- **Sources**: Product RAG source names appear as text citations, not arbitrary clickable filenames.
- **Limits**: Only simple Markdown, not full GitHub-Flavored Markdown, and only bar charts for appropriate known metrics; no fabricated line/pie/time-series charts. Historical session restore provides message text, not past structured charts/citations. Current session evidence is for the latest executed response.

Validation: `tests/test_rich_responses.py`, `tests/test_chat_branding.py`, and the existing chat/API/UI tests. Provider-backed LangGraph/LangSmith/RAGAS evidence is independent of this UI change.

## Files and validation
- `web/index.html` — semantic layout and preserved element IDs.
- `web/assets/styles.css` — legacy baseline tokens/components.
- `web/assets/data-workspace.css` — compact responsive layout overrides.
- `web/assets/app.js` — client-side safe data-table rendering and CSV export (no backend contract changes).
- `tests/test_data_first_ui.py` — structural, asset, privacy and data-first regression checks.
- Existing tests cover sessions, SSE, logs, ROI, and API behavior.

## Limits
- Frontend data table **does not execute SQL or compute business values**; it displays rows supplied by the existing agent backend.
- Restored chat history includes **message text**, not historical structured result records; the evidence pane is therefore cleared on session switch and reflects only the latest newly executed turn. Never imply old data is retained.
- The browser UI has **no remote LLM credentials**. A local Chromium preview using a mocked fetch/SSE response checks layout and rendering; it is not proof of real Azure/Chroma/LangSmith E2E.
- Keep synthetic data disclosures and illustrative ROI status visible, but avoid repeating warnings as large banners.

## Run
```bash
python -m pytest -q
python -m scripts.seed
uvicorn retailiq.api:app --host 127.0.0.1 --port 8000
```
Open http://127.0.0.1:8000 and select **Assistant**; ask a question and then a follow-up in the same session.
