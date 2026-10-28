# Official Week 1 Demo Checklist — Evidence Matrix

| Requested checkpoint | Status in this package | Where to demonstrate | Missing evidence / next step |
|---|---|---|---|
| Clear workflow and architecture | Documented | `docs/01_...`, `docs/02_...`, slides 2–6 | Validate business assumptions with sponsor if possible |
| FDE introduction | Described (not field-validated) | `docs/07_...`, FDE slide | Do not claim interviews with real clients |
| Harness layers and components | Documented | `docs/07_...`, harness slide | Explain trust and verification boundaries |
| Chain, Agent, subagent, handoff, skill, router, custom workflow | Router/custom workflow plus subagent, handoff and allowlisted skills implemented in the FDE extension | `docs/07_...`, `docs/10_FDE_MultiAgent_Session_Implementation.md`, pattern slide | Supervisor delegates to scoped specialist subgraphs; Week 4 still requires five mandated write-side agents |
| Harness observability and LangSmith operations | Local JSONL logs and UI implemented; LangSmith configured but not remotely verified | `retailiq/observability.py`, `retailiq/api/logs.py`, `docs/11_Logging_Observability.md`; LangSmith slide | Obtain separate LangSmith key, capture actual trace and model token evidence |
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

## Week 1 FDE multi-agent extension (post-checklist update)

- Router: model classification with fallback, typed LangGraph `Command` to specialist nodes.
- Subagent: Supervisor uses two LangChain `@tool`-wrapped scoped LangGraph graphs for SQL Sales/Inventory analytics.
- Handoff: a Sales→Inventory follow-up triggers a graph-level `Command` transfer and auditable metadata.
- Skill: on-demand allowlisted business instructions; Product Agent injects skill text into its grounding prompt.
- Chat sessions: local SQLite CRUD and bounded per-conversation context; UI session switching/delete supported.
- Local regression suite: **89 passed, 1 compiled-graph test module skipped (2026-10-28 local run)** because LangGraph is unavailable here. GitHub CI installs it and attempts the compiled graph smoke test.
- Local application observability: request/session correlation IDs, safe JSONL events, bounded rotation, agent/tool durations and loopback-only Execution Logs tab. Tests verify privacy and filtering. This is not LangSmith tracing.
- Remote LLM/Chroma/RAGAS/LangSmith E2E evidence is still outstanding and should not be claimed PASS.

## Execution Logs acceptance (2026-10-28)

- [x] Application-level structured logging; request ID returned in API headers/body.
- [x] Session-specific agent/tool/handoff events and local-only event viewer.
- [x] Failure stack frame locations recorded privately, never returned by API.
- [x] Tests ensure prompt text and secrets are not written to log file.
- [ ] LangSmith live trace + model usage; still requires real API credentials.

Evidence: `tests/test_observability.py`, `docs/11_Logging_Observability.md`.

## Course reading baseline and strict lesson audit (2026-10-28)

- [Lesson 02–05 sources supplied by the team](00_WEEK1_LESSON_REFERENCES.md) (23 entries; some repeated across lessons).
- [Detailed lesson-to-code compliance audit](13_WEEK1_LESSON_COMPLIANCE_AUDIT.md).
- Core harness layers are **Orchestration, Context Management, Tool Integration, Verification, Operations**; UI is outside the five-layer harness core.
- **Do not conflate** model-directed LangChain Supervisor (full mode, provider not yet verified) with deterministic LangGraph SQL subgraphs or offline fallback.
- **Do not conflate** local SSE app events with LangSmith nested run/trace/thread evidence, or ROI estimates with provider-measured costs.


## Week 1 runtime hardening and future-week deferrals (2026-10-28)

- [x] Single-process session mutation guard: simultaneous requests to one session return HTTP 409 (or a `session_busy` SSE error); separate sessions remain independent.
- [x] Session deletion logically removes LangGraph checkpoint state first; failed cleanup keeps the chat session and returns 503.
- [x] Minimal resilience: provider-call timeout configurable (default 20 s), one provider retry, up to two attempts on transient read-only SQL node errors.
- [ ] Full-mode compiled graph, LangSmith and RAGAS require real provider/runtime evidence; local tests are not substitutes.
- **Deferred:** advanced retries, whole-request cancellation, distributed locking, and long-term memory (Week 2); approval/RBAC/advanced cost governance (Week 3); write-side orders/pricing/fulfilment (Week 4).

## Code hardening completion (2026-10-28)

See [14_WEEK1_CODE_HARDENING.md](14_WEEK1_CODE_HARDENING.md) for applied patches, strict provider E2E commands, ten new offline tests, CI LangGraph gate, and remaining live LangSmith/RAGAS evidence.
