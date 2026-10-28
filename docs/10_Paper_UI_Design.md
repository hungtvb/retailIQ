# RetailIQ Week 1 — Data-first UI

## UX principle
This is an **operations workspace**, not a marketing landing page. The first screen should let retail managers **ask a question → read the answer → inspect structured data and sources → view agent execution** without scrolling past promotional copy.

## Current interface
- **Data Query**: compact session selector, query field and five sample queries. Conversation history is collapsed by default.
- **Answer**: direct response with execution status, selected agent, reference period and full/offline indication.
- **Data records**: rows from the real `records` API response displayed immediately as a sortable-looking but **non-sortable** semantic table (no implied sort affordance). Up to 200 rows rendered; actual row count shown. CSV export includes all returned records and guards against spreadsheet formula injection from string values.
- **Product sources**: unique filenames from retrieved contexts; plain text only (not invented clickable links).
- **Execution**: in-place SSE timeline; advanced metadata and raw JSON remain available under expandable details.
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
- Restored chat history does not include historical result records from the session endpoint, so previous answer text is shown but the records table clears until a query is run again.
- The browser UI has **no remote LLM credentials**. A local Chromium preview using a mocked fetch/SSE response checks layout and rendering; it is not proof of real Azure/Chroma/LangSmith E2E.
- Keep synthetic data disclosures and illustrative ROI status visible, but avoid repeating warnings as large banners.

## Run
```bash
python -m pytest -q
python -m scripts.seed
uvicorn retailiq.api:app --host 127.0.0.1 --port 8000
```
Open http://127.0.0.1:8000 and select **Data Query**.
