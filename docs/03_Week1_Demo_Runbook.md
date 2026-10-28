# Week 1 Demo Script — 6 minutes

| Time | Segment | On-screen action |
|---|---|---|
| 0:00–0:45 | Business domain | Explain omnichannel Electronics retailer and inventory/report pain points |
| 0:45–1:30 | Architecture | Graph: Intent → SQL tool or Product RAG |
| 1:30–2:15 | Stock | Ask AlphaBook stock, show 3 locations, distinguish on-hand / reserved / available |
| 2:15–3:00 | Revenue | Ask this month's revenue, show online/store breakdown and KPI formula |
| 3:00–3:40 | Top sellers | Ask top sellers by completed-order units sold |
| 3:40–4:30 | Product RAG | Ask about 65W charger; show source and vector retrieval in **full mode** |
| 4:30–5:20 | Evaluation | Show real LangSmith trace and RAGAS scores if available; otherwise disclose not yet run |
| 5:20–6:00 | Roadmap | Explain additions in W2, W3 and mandatory W4 agents |

## Preflight
Follow `docs/05_Huong_dan_OpenAI_Compatible_VI.md`: configure the shared OpenAI-compatible `.env`, run `python -m scripts.check_openai` then optionally `--live`, seed with `python -m scripts.seed`, run `pytest -q`, then `uvicorn retailiq.api:app --host 127.0.0.1 --port 8000`. Open browser at http://127.0.0.1:8000. Full mode requires installation/API keys. This edition defaults to full mode; use `RETAILIQ_MODE=offline` explicitly for the deterministic fallback. Without credentials or installed full dependencies, full mode is not yet E2E verified. Do not call offline mode LangGraph or vector RAG.

## Demo definitions
As-of fixed 2026-10-28 for seed repeatability. Net revenue excludes taxes/shipping/returns. Stock available is on_hand minus reserved, not on_hand alone.


## Official checklist presentation (additional slides)

Use `slides/RetailIQ_Flezi_Week1_Checklist_Aligned.pptx` for the graded demo. The additional slides cover:
- FDE: domain discovery → scoped prototype → feedback, with synthetic-data disclosure
- 5 harness layers and corresponding RetailIQ modules
- Router and custom-workflow patterns implemented; chain/agent/subagent/handoff/skill distinctions
- Token-based cost model and illustrative 3.75-month payback (not real business results)
- 43 local tests, open full-mode E2E, RAGAS and LangSmith verification gates

Present the pattern comparison and ROI slides quickly; reserve most demo time for the four questions and evidence. If LangSmith/RAGAS traces are unavailable, state they are not yet verified rather than presenting fabricated screenshots or scores.
