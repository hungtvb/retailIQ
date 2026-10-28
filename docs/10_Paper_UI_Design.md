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
