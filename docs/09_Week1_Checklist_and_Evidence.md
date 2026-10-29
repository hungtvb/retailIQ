# Official Week 1 Demo Checklist — Evidence Matrix

## Live verification on 2026-10-29

- `python -m scripts.full_e2e` passed all five full-mode cases: stock, revenue, top sellers, Product RAG, and replenishment review. The local machine used real model and embedding calls; see `data/full_e2e_report.json` (local, ignored by Git).
- The LangSmith project `retailiq-week1` returned successful remote root traces for those five requests, with nested router, specialist, reply, and `ChatOpenAI` runs. Example traces: [stock](https://smith.langchain.com/o/b2b60b66-94a2-4ec4-9bde-f3659243404f/projects/p/c0a76076-9285-45b3-96e0-aaef05d427e9/r/01a185c2-932a-74fd-9a6a-35e86bb3a267), [product RAG](https://smith.langchain.com/o/b2b60b66-94a2-4ec4-9bde-f3659243404f/projects/p/c0a76076-9285-45b3-96e0-aaef05d427e9/r/01a185c2-b113-70ef-991c-ea9bba0b002b), [replenishment review](https://smith.langchain.com/o/b2b60b66-94a2-4ec4-9bde-f3659243404f/projects/p/c0a76076-9285-45b3-96e0-aaef05d427e9/r/01a185c2-c63d-745f-bd3c-0cbf729da10d). The product trace has two successful model runs with token counts. Links require access to the project.
- Provider-backed RAGAS completed three product questions: faithfulness mean/min **1.000/1.000**; answer relevancy mean **0.729**, min **0.665**. The [complete score artifact](evidence/week1_ragas_2026-10-29.json) contains each case score and source count. This small synthetic set is not a general quality guarantee.
- The first RAGAS attempt exposed a real retrieval miss: the AlphaBook document scored 0.430 against the former 0.45 relevance threshold. The demo threshold is now 0.40; the same question retrieves the correct document, while two unrelated probes returned no contexts. The passing report reflects this updated configuration. RAGAS 0.4.3 also required `langchain-community<0.4.2` to import successfully.
- The local `full_e2e_report.json` still shows `langsmith_remote_trace_verified=false` and `ragas_scores_verified=false` because that script does not perform those later checks. The remote trace inspection and separate RAGAS run above provide the evidence; those booleans must not be read as the current aggregate status.

| Requested checkpoint | Status in this package | Where to demonstrate | Missing evidence / next step |
|---|---|---|---|
| Clear workflow and architecture | Documented | `docs/01_...`, `docs/02_...`, slides 2–6 | Validate business assumptions with sponsor if possible |
| FDE introduction | Described (not field-validated) | `docs/07_...`, FDE slide | Do not claim interviews with real clients |
| Harness layers and components | Documented | `docs/07_...`, harness slide | Explain trust and verification boundaries |
| Chain, Agent, subagent, handoff, skill, router, custom workflow | Router/custom workflow plus subagent, handoff and allowlisted skills implemented in the FDE extension | `docs/07_...`, `docs/10_FDE_MultiAgent_Session_Implementation.md`, pattern slide | Supervisor delegates to scoped specialist subgraphs; Week 4 still requires five mandated write-side agents |
| Harness observability and LangSmith operations | Live remote traces verified 2026-10-29 | `retailiq/observability.py`, `retailiq/api/logs.py`, `docs/11_Logging_Observability.md`; trace links above | Show the trace tree and token usage in the demo |
| Cost and ROI | Calculated with explicit assumptions | `scripts/cost_roi.py`, `docs/08_...`, ROI slide | Obtain measured baselines and actual provider rates |
| Demo success | Five full-mode scripted cases passed 2026-10-29 | `data/full_e2e_report.json` on demo machine; trace links above | Natural-language robustness remains limited outside scripted cases |
| Testing, limitations and risks | Deterministic tests plus three live RAGAS scores; retrieval miss found and addressed | `tests/`, score artifact above | Expand the evaluation set and calibrate retrieval threshold on more positive/negative cases |

**Current status:** The dated live evidence above supersedes the earlier offline-only snapshot. It verifies scripted full-mode paths, a small RAGAS set, and remote LangSmith traces; it does not validate open-ended retail questions or production quality.

## Pre-demo gate
- [ ] `python -m scripts.seed` + `python -m pytest -q` pass
- [ ] `python -m scripts.check_openai --live` succeeds (secrets stay in local .env)
- [x] `RETAILIQ_MODE=full` and five scripted scenarios returned valid, correctly sourced answers on 2026-10-29
- [x] `python -m scripts.eval_ragas` wrote real judge results; the first failed attempt and threshold adjustment are recorded above
- [x] LangSmith project contains verified traces for the scripted cases
- [ ] Architecture, FDE, agent pattern choices and ROI assumptions explained in slides
- [ ] Run risks: no production auth, synthetic data, missing freshness/guardrails

## Cost & ROI dashboard update

A local **Cost & ROI** tab now calculates business benefits, estimated LLM and embedding token costs, payback, and sensitivity. It is an **illustrative financial model**, not a measured agent-operation cost report. Evidence: `retailiq/api/roi.py`, `retailiq/domain/economics.py`, `web/index.html`, `tests/test_roi_dashboard.py`, [`docs/ui_previews/roi_desktop.png`](ui_previews/roi_desktop.png). LangSmith token counts are visible in the verified traces, but they have not been reconciled with this ROI model.

## Week 1 FDE multi-agent extension (post-checklist update)

- Router: model classification with fallback, typed LangGraph `Command` to specialist nodes.
- Subagent: Supervisor uses two LangChain `@tool`-wrapped scoped LangGraph graphs for SQL Sales/Inventory analytics.
- Handoff: a Sales→Inventory follow-up triggers a graph-level `Command` transfer and auditable metadata.
- Skill: on-demand allowlisted business instructions; Product Agent injects skill text into its grounding prompt.
- Chat sessions: local SQLite CRUD and bounded per-conversation context; UI session switching/delete supported.
- Current main CI on code commit `224fcb7`: **276 Python and 12 Node tests passed**; the separate quality workflow passed mocked compiled-graph and localhost E2E checks. See [dated test evidence](06_Test_Evidence.md). A later local live-provider run is documented above.
- Local application observability: request/session correlation IDs, safe JSONL events, bounded rotation, agent/tool durations and loopback-only Execution Logs tab. Tests verify privacy and filtering. This is not LangSmith tracing.
- Remote LLM/Chroma/RAGAS/LangSmith evidence was obtained on 2026-10-29 for the limited scripted set described above.

## Execution Logs acceptance (2026-10-28)

- [x] Application-level structured logging; request ID returned in API headers/body.
- [x] Session-specific agent/tool/handoff events and local-only event viewer.
- [x] Failure stack frame locations recorded privately, never returned by API.
- [x] Tests ensure prompt text and secrets are not written to log file.
- [x] LangSmith live trace + model token usage verified on 2026-10-29 (trace links above).

Evidence: `tests/test_observability.py`, `docs/11_Logging_Observability.md`.

## Course reading baseline and strict lesson audit (2026-10-28)

- [Lesson 02–05 sources supplied by the team](00_WEEK1_LESSON_REFERENCES.md) (23 entries; some repeated across lessons).
- [Detailed lesson-to-code compliance audit](13_WEEK1_LESSON_COMPLIANCE_AUDIT.md).
- Core harness layers are **Orchestration, Context Management, Tool Integration, Verification, Operations**; UI is outside the five-layer harness core.
- **Do not conflate** model-directed LangChain Supervisor with deterministic LangGraph SQL subgraphs or offline fallback; the full-mode scripted run was verified on 2026-10-29.
- **Do not conflate** local SSE app events with LangSmith nested run/trace/thread evidence, or ROI estimates with provider-measured costs.


## Week 1 runtime hardening and future-week deferrals (2026-10-28)

- [x] Single-process session mutation guard: simultaneous requests to one session return HTTP 409 (or a `session_busy` SSE error); separate sessions remain independent.
- [x] Session deletion logically removes LangGraph checkpoint state first; failed cleanup keeps the chat session and returns 503.
- [x] Minimal resilience: provider-call timeout configurable (default 20 s), one provider retry, up to two attempts on transient read-only SQL node errors.
- [x] Full-mode compiled graph, LangSmith and RAGAS have real provider/runtime evidence for the dated scripted run above; local tests remain separate evidence.
- **Deferred:** advanced retries, whole-request cancellation, distributed locking, and long-term memory (Week 2); approval/RBAC/advanced cost governance (Week 3); write-side orders/pricing/fulfilment (Week 4).

## Code hardening completion (2026-10-28)

See [14_WEEK1_CODE_HARDENING.md](14_WEEK1_CODE_HARDENING.md) for applied patches, strict provider E2E commands, ten new offline tests, CI LangGraph gate, and remaining live LangSmith/RAGAS evidence.
