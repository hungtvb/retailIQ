# Week 1 — Local setup and demonstration

> **Team Python baseline: 3.12.** Run from repository root. Keep `.env`/API keys out of Git. Install RAGAS into the **same environment** after app dependencies; no second interpreter needed.

## Windows PowerShell

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -U pip
.\.venv\Scripts\python.exe -m pip install -r requirements-full.txt
Copy-Item .env.example .env
```

## Linux/macOS

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -U pip
python -m pip install -r requirements-full.txt
cp .env.example .env
```

Set `RETAILIQ_MODE=full`, `OPENAI_BASE_URL` (base URL, not the completions endpoint), `OPENAI_API_KEY`, `CHAT_MODEL` and `EMBEDDING_MODEL` in `.env`. For remote traces set a separate `LANGSMITH_API_KEY` and `LANGSMITH_TRACING=true`.

## Verify and start

```bash
python -m scripts.check_openai
python -m scripts.check_openai --live
python -m scripts.seed
python -m scripts.index_rag --dry-run
python -m scripts.index_products
python -m pytest -q -rs
python -m scripts.full_e2e
python -m uvicorn retailiq.api:app --host 127.0.0.1 --port 8000
```

Open `http://127.0.0.1:8000`. **Warning:** `scripts.seed` recreates the synthetic retail data and generated product docs. Do not run it on local custom data without backup.

## RAGAS and acceptance

```bash
python -m pip install -r requirements-eval.txt
python -m pip check
python -m scripts.eval_ragas
node --test tests/frontend_format.test.cjs
python -m scripts.quality_gate --samples 50
```

If `scikit-network` attempts a C++ build on Windows/Python 3.14, use the Python 3.12 venv first rather than installing another runtime for RAGAS. Offline mode is `RETAILIQ_MODE=offline` with `requirements-offline.txt`; it is **not** proof of LangGraph provider, Chroma, LangSmith or RAGAS live execution.

## Demo sequence — all seven grading criteria

1. Explain Business Problem, target users and expected value from [PROJECT](../../PROJECT.md) (**BP-1..3**).
2. Explain workflow, trustworthy SQL/Product RAG and architecture from [ARCHITECTURE](../../ARCHITECTURE.md) (**SD-1**).
3. Show FDE, five harness layers, LangChain agent patterns, LangSmith and cost/ROI assumptions with [DESIGN](DESIGN.md) (**SD-2**).
4. Run stock, monthly revenue, top-sellers, product RAG and one appropriate cross-source example (**SD-3**).
5. Show real RAGAS/LangSmith artifacts, deterministic tests, open gaps, risk and improvements from [EVIDENCE](EVIDENCE.md) (**SD-4**).

**Presentation drafts:** [PPTX](assets/RetailIQ_Flezi_Week1_Checklist_Aligned.pptx) · [DOCX](assets/RetailIQ_Business_Architecture_Week1.docx). These assets predate the *new Business Problem rubric* and have **not** been updated/approved for all seven checkpoints.

## Failure handling

| Problem | Response |
|---|---|
| `ModuleNotFoundError` | Check `python --version`, active `.venv` and install dependencies with that exact interpreter |
| Provider/embedding errors | Verify keys, base URL and model/deployment; run `scripts.check_openai --live` |
| Product search empty | Rebuild index, check embedding and citations; no stock claims from product documents |
| LangSmith trace absent | Confirm **full** mode, tracing keys and that a genuine request ran |
| RAGAS import/build errors | Check Python **3.12** and `requirements-eval.txt`; do not mark PASS on an import alone |
| Unexpected agent path | Inspect session/request-specific events, executed tools and returned evidence, not a static mock UI |

Bind the app to `127.0.0.1`; no production authentication, multi-tenant isolation or freshness SLA is provided. See the [archived original runbook](../../archive/2026-10-30/legacy/03_Week1_Demo_Runbook.md) for the prior longer walkthrough.
