# Official Week 1 Demo Checklist — Evidence Matrix

| Requested checkpoint | Status in this package | Where to demonstrate | Missing evidence / next step |
|---|---|---|---|
| Clear workflow and architecture | Documented | `docs/01_...`, `docs/02_...`, slides 2–6 | Validate business assumptions with sponsor if possible |
| FDE introduction | Described (not field-validated) | `docs/07_...`, FDE slide | Do not claim interviews with real clients |
| Harness layers and components | Documented | `docs/07_...`, harness slide | Explain trust and verification boundaries |
| Chain, Agent, subagent, handoff, skill, router, custom workflow | Router/tool/custom flow implemented conceptually; comparison for other patterns | `docs/07_...`, pattern slide | Only Week 4 will implement actual multi-agent; do not mislabel document files as skills |
| LangSmith operations | Configured but not remotely verified | `core/config.py`, LangSmith slide | Obtain separate LangSmith key, capture trace and timing/token evidence |
| Cost and ROI | Calculated with explicit assumptions | `scripts/cost_roi.py`, `docs/08_...`, ROI slide | Obtain measured baselines and actual provider rates |
| Demo success | Offline local proof; full mode unverified | `GET /`, `/ask`, runbook | Run real LangGraph + Chroma with actual API credentials |
| Testing, limitations and risks | Deterministic pytest + tests for loaders / UI, documented limitations | `tests/`, `docs/06_...`, `docs/07_...` | RAGAS scores, LangSmith trace, full E2E negative tests remain |

**STRICT STATUS:** No live RAGAS scores, LangSmith trace, or live external LLM run are claimed. Unit tests/mocked client tests do not validate these features.

## Pre-demo gate
- [ ] `python -m scripts.seed` + `python -m pytest -q` pass
- [ ] `python -m scripts.check_openai --live` succeeds (secrets stay in local .env)
- [ ] `RETAILIQ_MODE=full` and 4 `/ask` scenarios return valid, correctly sourced answers
- [ ] `python -m scripts.eval_ragas` writes real judge results; review failures honestly
- [ ] LangSmith project contains actual sample traces, or disclose incomplete tracing
- [ ] Architecture, FDE, agent pattern choices and ROI assumptions explained in slides
- [ ] Run risks: no production auth, synthetic data, missing freshness/guardrails

## Cost & ROI dashboard update

A local **Cost & ROI** tab now calculates business benefits, estimated LLM and embedding token costs, payback, and sensitivity. It is an **illustrative financial model**, not a measured agent-operation cost report. Evidence: `retailiq/api/roi.py`, `retailiq/domain/economics.py`, `web/index.html`, `tests/test_roi_dashboard.py`, `docs/retailiq_cost_roi_ui_preview.png`. Actual LangSmith token measurements remain outstanding.
