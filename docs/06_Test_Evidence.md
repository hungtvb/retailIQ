# Week 1 OpenAI-Compatible Integration — Local Test Evidence

Validated in a credentials-free build environment.

| Verification | Result | Meaning |
|---|---|---|
| `python -m scripts.seed` | PASS: 10 products, 30 inventory records, 120 orders | Synthetic data seeded |
| `python -m pytest -q` | 43/43 PASS | SQL, routing, endpoint/key sharing, Azure v1 normalization, invalid URL validation, mocked provider factories, tracing controls |
| `python -m scripts.check_openai` | PASS dry-run | Prints missing configuration when real env not provided, no requests made |
| Local HTTP smoke test | 5/5 PASS | FastAPI `/health` + 4 offline query intents via `TestClient` |
| External OpenAI-compatible chat + embedding | NOT TESTED | No user credential available here |
| LangGraph + Chroma real end-to-end | NOT TESTED | Full dependencies/API credential not available here |
| RAGAS scores | NOT TESTED | Requires live API |
| LangSmith traces | NOT TESTED | LangSmith key not configured |

The tests use fabricated keys and mocks. **No external API call has been made and no user secret is bundled.** Run `python -m scripts.check_openai --live`, the four demo questions, and `python -m scripts.eval_ragas` before claiming full Week 1 completion.

## Audit update (Checklist-Ready package)

- Fixed local UI file path after API modularization: `GET /` now returns HTTP 200.
- Added 7 HTTP regression tests for root/health, four supported question intents, invalid input.
- Added 9 multi-format ingestion tests covering MD/TXT/PDF/DOCX/CSV/XLSX/JSON/HTML and chunk source metadata.
- Added ROI calculator tests and full-mode graph dispatch test.
- Fixed `.env` load order so `RETAILIQ_MODE=full` is read during API startup instead of silently using offline mode.
- Latest local suite: **43/43 PASS**. Live LLM/LangGraph/Chroma/RAGAS/LangSmith remain **NOT VERIFIED**; package does not include user keys.
