# RetailIQ Copilot

Local Week 1 demo for synthetic retail inventory, sales analytics, product knowledge, and agent routing. The fixture has 10 products, 3 locations, and 120 orders; the reference date defaults to `2026-10-28`.

**Business problem:** Retail staff may need to navigate multiple existing POS/BI/ERP/WMS tools, filters and reports to find and combine data. **RetailIQ's proposed outcome is Faster · Easier · Reliable completion of retail operational information tasks through natural-language conversation**, with trusted evidence. Inventory & Sales are the initial domains; the **top-seller Replenishment Review** is one cross-source *demo scenario*, not the full product purpose. **Faster/Easier are unvalidated hypotheses**, not measured time savings or UX improvements; this is not demand forecasting or automated ordering.

## Full-mode quick start

Requires Python 3.11+ and an OpenAI-compatible chat and embedding provider.

```bash
python -m venv .venv
# Linux/macOS
source .venv/bin/activate
# Windows PowerShell: .venv\Scripts\Activate.ps1
pip install -r requirements-full.txt
cp .env.example .env
```

Set `OPENAI_BASE_URL` and `OPENAI_API_KEY` in `.env`, then run:

```bash
python -m scripts.seed
python -m scripts.index_products
python -m scripts.full_e2e
uvicorn retailiq.api:app --host 127.0.0.1 --port 8000
```

Open <http://127.0.0.1:8000>. Run `python -m pytest -q -rs` for local tests. LangSmith tracing needs its own key and `LANGSMITH_TRACING=true`.

### Offline mode

Install `requirements-offline.txt` and set `RETAILIQ_MODE=offline` in `.env`. Offline mode supports deterministic SQL and lexical retrieval; it does not prove full LangGraph, Chroma, RAGAS, or LangSmith execution.

## Project documents

| Need | Start here |
|---|---|
| Scope and rubric | [Requirements](docs/00_PROJECT_REQUIREMENTS.md) · [Week 1 checklist](docs/00_WEEK1_OFFICIAL_CHECKLIST.md) · [Lesson references](docs/00_WEEK1_LESSON_REFERENCES.md) |
| Business problem and roadmap | [Business problem & goals](docs/01_Domain_Selection_and_Business_Problem.md) · [Scope & featured scenarios](docs/21_INVENTORY_SALES_BUSINESS_SCOPE.md) · [Synthetic pilot and its limits](docs/23_INTERNAL_SYNTHETIC_BUSINESS_PILOT.md) · [PRD](docs/12_Product_Brief_and_PRD.md) · [Four-week timeline](docs/16_Roadmap_and_Timeline.md) |
| Setup and demo | [Runbook](docs/03_Week1_Demo_Runbook.md) · [OpenAI-compatible setup](docs/05_Huong_dan_OpenAI_Compatible_VI.md) · [Slides](docs/slides/README.md) |
| Data, API, and acceptance | [Data/API contract](docs/13_Data_and_API_Contract.md) · [Traceability](docs/14_Requirements_Traceability.md) · [Test evidence](docs/06_Test_Evidence.md) |
| Engineering and operations | [Quality standard](docs/15_MODULE_QUALITY_STANDARD.md) · [Inventory/Sales](docs/16_INVENTORY_SALES_HARDENING.md) · [Product RAG](docs/17_PRODUCT_RAG_MODULE_HARDENING.md) · [Agent harness](docs/18_AGENT_HARNESS_HARDENING.md) · [Risk register](docs/15_Risk_Register_and_Document_Governance.md) |
| Presentation | [Slide guide and deck](docs/slides/README.md) |

## Verification status

Use [test evidence](docs/06_Test_Evidence.md) and [traceability](docs/14_Requirements_Traceability.md) for dated results. On code commit `a7f3bf6`, [main regression CI](https://github.com/hungtvb/retailIQ/actions/runs/40723434409) passed **283 Python tests + 12 frontend tests** and [synthetic pilot CI](https://github.com/hungtvb/retailIQ/actions/runs/40723434470) passed 7 focused tests. These are **local/mocked technical checks**, not live LLM/Chroma, RAGAS, LangSmith or measured human business value. See [traceability](docs/14_Requirements_Traceability.md).

**Security:** `.env` is gitignored. Use synthetic data, bind to `127.0.0.1`, and do not expose this unauthenticated demo publicly.
