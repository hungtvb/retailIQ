# RetailIQ Copilot — Week 1 (Single OpenAI-Compatible API)

**Project:** RetailIQ Copilot – Omnichannel Inventory Intelligence & Conversational Analytics  
**Week 1:** Local Inventory & Sales SQL assistant, Product RAG with Chroma, LangGraph routing, RAGAS evaluation, optional LangSmith tracing.  
**Synthetic data:** 10 products, 3 locations, 30 inventory rows, 120 orders, fixed demo date `2026-10-28`.

## Minimal configuration

For **both chat and embedding**, use the same `OPENAI_BASE_URL` and `OPENAI_API_KEY`. If your gateway recognizes the default model names, these are the only two provider settings you must fill:

```dotenv
OPENAI_BASE_URL=https://YOUR-RESOURCE.openai.azure.com/openai/v1/
OPENAI_API_KEY=YOUR_LOCAL_API_KEY
```

The default chat/embedding model names are `gpt-4o-mini` and `text-embedding-3-small`.
**Azure uses deployment names as model IDs in requests.** If deployment names differ, edit **only** `CHAT_MODEL` and `EMBEDDING_MODEL` in `.env` (they are not keys or extra endpoints).

OpenAI base URL also supported (`https://api.openai.com/v1/`), plus other HTTPS OpenAI-compatible gateways. Azure resource root URLs (`https://RESOURCE.openai.azure.com/`) are normalized to `/openai/v1/`. The old Azure classic `/openai/deployments/...` + `api-version` route is **not** supported by this simplified edition.

## Local setup

```bash
python -m venv .venv
# Linux/macOS
source .venv/bin/activate
# Windows PowerShell: .venv\Scripts\Activate.ps1
pip install -r requirements-full.txt
cp .env.example .env           # Windows: Copy-Item .env.example .env
# Edit OPENAI_BASE_URL and OPENAI_API_KEY; adapt model names only if required.
python -m scripts.check_openai           # config dry-run, no requests
python -m scripts.check_openai --live    # 1 real chat + 1 real embedding request
python -m scripts.seed
python -m pytest -q
uvicorn retailiq.api:app --host 127.0.0.1 --port 8000
```

Open `http://127.0.0.1:8000`. **No-key smoke test:** set `RETAILIQ_MODE=offline` and install `requirements-offline.txt`. This uses SQL and lexical retrieval; it does **not** fulfill LangGraph/Chroma/RAGAS rubric.


## Week 1 — Cost & ROI Dashboard (now integrated into the local UI)

The original `python -m scripts.cost_roi` prints an **illustrative estimate to the terminal only**. The updated app also has a **Cost & ROI** tab at `http://127.0.0.1:8000/`, next to **AI Assistant**. It calls a local, read-only calculator API and needs no LLM key to run.

- `GET /api/roi/defaults`: example inputs, without credentials.
- `POST /api/roi/estimate`: validates assumptions and returns gross/net monthly benefit, payback, time saved, token spend forecast (USD), and 10/30/60% sensitivity scenarios.
- Token counts and rate inputs are **editable estimates**, not observed LangSmith traces or Azure price quotes.
- The VND monthly operating budget is **all-in (including planned AI spending)**. The USD token forecast is for transparency, *not* a second deduction.
- No data is persisted by these endpoints; invalid or negative values return HTTP 422.

For the live presentation, open **Cost & ROI**, modify assisted share from **60%** to **30%**, then click **Calculate estimate**: payback changes from **3.75** to **10.00 months**. At **10%**, the monthly net benefit is negative and payback is **not achieved**.

A visual preview is at `docs/retailiq_cost_roi_ui_preview.png`. Browser interactions were checked in Chromium with mock API responses generated from the actual FastAPI calculator; direct loopback browser navigation was restricted in the test container. Unit/API tests are automated and require no external API.

## Week 1 demo queries

1. `How many units of AlphaBook Pro 14 are currently in stock?`
2. `What is the revenue this month?`
3. `Which products are top sellers?`
4. `Tell me about USB-C GaN Charger 65W`

## Evaluation and tracing

```bash
python -m scripts.eval_ragas
```

Requires the full dependencies and live API. Records faithfulness/answer relevancy in `data/ragas_results.json`. No quality score is claimed without a real run.

LangSmith is **not needed for local chat functionality**, but **is in the official Week 1 rubric**. With `LANGSMITH_TRACING=false`, traces will not appear in LangSmith. Create LangSmith API key separately when ready.

## Definitions

- Available stock = `on_hand - reserved`, totaled across 3 locations.
- Revenue = completed order line subtotal after discounts; before returns/refunds/tax/shipping.
- Top sellers = number of completed order units in current synthetic month.
- Deterministic reference date = `2026-10-28` (`RETAILIQ_AS_OF`).

## Project roadmap

Week 2: freshness-aware routing, governed semantic layer, MCP inventory/order APIs, advanced RAG/memory.  
Week 3: governance/security/HITL for pricing, LangFuse, DeepEval, cost and security reports.  
Week 4: five mandatory domain agents, A2A, verification and manager-approved order scenario.

**Security:** `.env` is gitignored. Never paste API keys in chat, GitHub, slides or logs. The checker logs only readiness/models, never keys or endpoint URLs. Only bind `127.0.0.1` for local demo.

## Week 1 official checklist alignment

Start with `docs/09_Week1_Checklist_and_Evidence.md`, `docs/07_FDE_Harness_and_Patterns.md`, and `docs/08_Agent_Cost_ROI.md`. `scripts/cost_roi.py` is a fully local illustrative cost/ROI calculator. A new regression test explicitly checks `GET /` after the API modularization fix. The slide deck includes FDE, harness layers, pattern choice and cost/ROI.

**Do not call unit-test success an end-to-end LangGraph/RAGAS/LangSmith PASS.** Real model credentials and a separate LangSmith key are needed for proof.

## Week 1 UI — Paper & Highlighter redesign

The `web/` interface follows the supplied **DESIGN 7.md / Pirsch Analytics** style reference. It uses a warm paper canvas (`#f8f5ed`), ink-black hairlines, sunshine yellow (`#ffda6e`) as the only prominent call-to-action color, and restrained mint (`#6ece9d`) for status. The UI uses DM Sans from Google Fonts when available; offline machines automatically fall back to installed Inter/system sans. No font files are bundled.

- `web/index.html` — semantic markup for AI Assistant + Cost & ROI tabs.
- `web/assets/styles.css` — shared tokens, components and mobile layout.
- `web/assets/app.js` — questions, tab switching and ROI calculations using existing APIs.
- `GET /assets/styles.css`, `GET /assets/app.js` — served locally by FastAPI.

No backend calculation, SQL query, model setting or ROI business assumption was changed. UI is entirely static and does not read API keys. Run `uvicorn retailiq.api:app --host 127.0.0.1 --port 8000` and open the root URL.
