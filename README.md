# RetailIQ Copilot

Local Week 1 demo for synthetic retail inventory, sales analytics, product knowledge, and agent routing. The fixture has 10 products, 3 locations, and 120 orders; the reference date defaults to `2026-10-28`.

**Business problem:** Retail staff may need to navigate multiple existing POS/BI/ERP/WMS tools, filters and reports to find and combine data. **RetailIQ's proposed outcome is Faster · Easier · Reliable completion of retail operational information tasks through natural-language conversation**, with trusted evidence. Inventory & Sales are the initial domains; the **top-seller Replenishment Review** is one cross-source *demo scenario*, not the full product purpose. **Faster/Easier are unvalidated hypotheses**, not measured time savings or UX improvements; this is not demand forecasting or automated ordering.

## Full-mode quick start

**If chat reports a missing Python module:** Make sure the server uses the same
Python environment where full dependencies were installed:

```bash
python -m pip install -r requirements-full.txt
python -c "from langgraph.checkpoint.sqlite import SqliteSaver; print('Checkpoint OK')"
```

Start the server with `python -m uvicorn retailiq.api:app --host 127.0.0.1 --port 8000`
using that same Python interpreter. `ModuleNotFoundError: retailiq.*` usually
means source files or the working directory are out of sync; update the project
and restart instead of installing a similarly named external package.


Requires Python 3.11+ and an OpenAI-compatible chat and embedding provider.

`requirements-full.txt` installs the application runtime (chat, agents, LangGraph,
Chroma, LangSmith) **without RAGAS**. For the separate course evaluation step,
install `requirements-eval.txt` and then run `python -m scripts.eval_ragas`.
RAGAS brings in `scikit-network`; it is not needed to chat. On a platform
without a compatible prebuilt wheel, this separation avoids requiring a C/C++
compiler merely to start RetailIQ.

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

The chat presents RetailIQ as the speaker. Specialist agents work behind the scenes and remain visible in execution details. Greetings and ordinary conversation use a general chat route; inventory, sales, and product claims still use the bounded data routes. Vietnamese questions receive Vietnamese answers where the underlying evidence is available. The data-record table is collapsed by default and can be opened for inspection or CSV export.
Short follow-up questions can reuse a product explicitly named by the user or selected by a reviewed “newest” or “top seller” query in the same chat. RetailIQ does not infer a product from untrusted assistant prose, and a new unrelated topic ends that reference chain.
Sales and top-seller questions use the month named in the question; when no month is given, they use `RETAILIQ_AS_OF`. “Tháng 9” without a year means September of the configured reference year.
“Newest products” uses `products.catalog_added_at` from the synthetic catalog; it does not claim a market release date. Re-run `python -m scripts.seed` after updating an older local database to add this field.

### Source ownership (Week 1)

- `retailiq/assistant.py` is the public entrypoint; `retailiq/orchestration/week1_graph.py` owns routing, handoff, and supervisor workflow.
- `retailiq/queries.py` holds the shared bounded query dispatch; `retailiq/reply.py` formats the final user-facing answer. Neither module depends on the orchestration graph.
- `retailiq/domain/analytics.py` is the reviewed read-only SQL and metric source of truth; `retailiq/rag/` handles product retrieval. Week 1 does **not** generate arbitrary SQL.
- `scripts/seed.py` is the reproducible synthetic data generator. Do not edit the generated SQLite or product documents by hand; reseeding replaces the dataset.

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

Use [test evidence](docs/06_Test_Evidence.md) and [traceability](docs/14_Requirements_Traceability.md) for dated results. The dated 2026-10-29 demo-machine evidence records five scripted full-mode cases, three provider-backed RAGAS samples, and remote LangSmith traces; see [Week 1 evidence](docs/09_Week1_Checklist_and_Evidence.md). CI regression and mocked-provider E2E results are separate from those live checks. None of these establishes open-ended conversational correctness or real business ROI.

**Security:** `.env` is gitignored. Use synthetic data, bind to `127.0.0.1`, and do not expose this unauthenticated demo publicly.
