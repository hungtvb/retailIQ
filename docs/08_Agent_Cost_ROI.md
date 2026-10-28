# Week 1 — Agent Cost and ROI Estimation

**Purpose:** demonstrate a defensible estimation method, **not** assert real business ROI for the synthetic retailer.

## 1. Cost drivers

| Cost bucket | Drivers / formula | Source needed |
|---|---|---|
| LLM input | Requests × average input tokens / 1,000,000 × model input price | LangSmith token usage; actual model rate |
| LLM output | Requests × average output tokens / 1,000,000 × model output price | LangSmith output usage; actual model rate |
| Embeddings | Indexed/query tokens / 1,000,000 × embedding rate | Embedding usage and provider rate |
| Tool, storage & infrastructure | Chroma/SQLite local demo ≈ no separate paid server; production could incur hosting costs | Deployment estimates |
| RAGAS / evaluation | Eval cases × LLM-judge token costs | Test schedule, evaluation trace |
| Support & maintenance | Logging, monitoring, troubleshooting, updates | Team effort estimate |

**Caution:** A question routed through LangGraph may invoke the chat model for routing, and a product question may also invoke a separate answer-generation LLM call. Count **all calls** in averages. The code uses a read-only SQL path for numeric answers.

## 2. Illustrative monthly business case (VND)

- 1,000 eligible inquiries / month (assumption)
- 60% of inquiries see a time reduction (assumption)
- 4 minutes saved per affected inquiry (assumption)
- 150,000 VND fully-loaded labor cost / hour (assumption)
- 1,200,000 VND per month service/operating cost (assumption; includes hypothetical model/ops budget)
- 18,000,000 VND initial build cost (assumption)

Gross benefit = 1,000 × 0.60 × 4 / 60 × 150,000 = **6,000,000 VND/month**.

Net monthly benefit = 6,000,000 − 1,200,000 = **4,800,000 VND/month**.

Simple payback = 18,000,000 / 4,800,000 = **3.75 months**.

These values are **not observed**, **not provider pricing** and should never be presented as actual savings. If net monthly benefit ≤ 0 there is no finite payback in this simple model.

## 3. Sensitivity analysis

If affected share is 30% instead of 60%, gross benefit = 3,000,000 and monthly net benefit = 1,800,000 VND; payback = **10 months**. If only 10% of inquiries benefit, gross = 1,000,000 VND, net = −200,000, so payback is **not achieved**.

## 4. What is needed for real ROI
Measure manual handling time by question type with staff; capture baseline request volume; measure response quality and the *actual* reduction in working time; track model usage using LangSmith; use current Azure/model prices; include failed/inaccurate responses, retries and maintenance. Recompute before claiming savings.

Use the local script: `python -m scripts.cost_roi`.

## 5. Interactive Week 1 UI demonstration

Open the local web app at `http://127.0.0.1:8000/` and choose **Cost & ROI**. This screen is part of the **same app** as the assistant, not an external script. The finance endpoint computes estimates in-process without using API keys.

Demo steps: (1) show baseline assumptions (1,000 questions/month, 60% assisted, 4 minutes saved, 150,000 VND/hour); (2) read gross benefit = 6,000,000 VND, net = 4,800,000 VND, payback = 3.75 months; (3) adjust assisted share to 30% to show 10-month payback; (4) set 10% to show no payback.

The right panel estimates monthly token spending from **user-entered** average tokens and USD-per-million rates. Do not present these as Azure invoice values. The all-in VND operating budget already includes model spending; token forecast is shown separately to avoid currency-mismatch and double-counting. Actual request token telemetry and current contracted Azure rates would be required for a real agent cost calculation.

Endpoints: `GET /api/roi/defaults`, `POST /api/roi/estimate`. Business calculation source: `retailiq/domain/economics.py`; request schema: `retailiq/api/roi.py`; UI: `web/index.html`. The CLI entrypoint remains available for script-based demos.
