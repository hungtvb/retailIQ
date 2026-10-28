# RetailIQ Copilot

Local Week 1 demo for synthetic retail inventory, sales analytics, product knowledge, and agent routing. The fixture has 10 products, 3 locations, and 120 orders; the reference date defaults to `2026-10-28`.

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
| Product and schedule | [PRD](docs/12_Product_Brief_and_PRD.md) · [Data/API contract](docs/13_Data_and_API_Contract.md) · [Traceability](docs/14_Requirements_Traceability.md) |
| Setup and operations | [Runbook](docs/03_Week1_Demo_Runbook.md) · [Risk register](docs/15_Risk_Register_and_Document_Governance.md) |
| Engineering hardening | [Quality standard](docs/15_MODULE_QUALITY_STANDARD.md) · [Inventory/Sales](docs/16_INVENTORY_SALES_HARDENING.md) · [Product RAG](docs/17_PRODUCT_RAG_MODULE_HARDENING.md) · [Agent harness](docs/18_AGENT_HARNESS_HARDENING.md) |
| Presentation | [Slide guide and deck](docs/slides/README.md) |

## Verification status

Use [test evidence](docs/06_Test_Evidence.md) and [traceability](docs/14_Requirements_Traceability.md) for current results. The recorded local snapshot reports 89 passed and 1 skipped; CI and live LLM/Chroma, RAGAS, and LangSmith evidence remain unverified there.

**Security:** `.env` is gitignored. Use synthetic data, bind to `127.0.0.1`, and do not expose this unauthenticated demo publicly.
