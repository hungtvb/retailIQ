# Week 1 — Dated Execution Evidence (Historical)

> **Consolidated:** 2026-10-30 from dated source documents. **HEAD before documentation migration:** `b1274762f939914ef712220e0b1f4299bccf41c6`. Results below apply to their **recorded date, SHA and execution mode**, not automatically to this new HEAD. Evidence and historical notes are preserved in [archive](../../archive/README.md).

**Ownership note:** this page preserves dated course/demo results and their original scope. It is **not** the live status ledger for the latest `main`. For present capability-level gaps consult [Capability Acceptance Ledger](../../29_COURSE_CAPABILITY_ACCEPTANCE_LEDGER.md), and for test case definitions/reproduction consult [Testing & Scenario Acceptance](../../27_BEHAVIORAL_ACCEPTANCE_MATRIX.md). Do not infer a current PASS from the provider traces or CI outcomes below without matching SHA/mode evidence.

**Status vocabulary:** PASS — local deterministic; PASS — mocked LangGraph; PASS — provider-backed, with real endpoint/model; DOCUMENTED only; NOT VERIFIED for the current revision; PLANNED for later weeks.

## Week 1 evidence ledger

| Scope / rubric | Date / SHA | Execution evidence | Accurate status |
|---|---|---|---|
| Business Problem BP-1..3 | Working hypothesis selected 2026-10-28 | [PROJECT](../../PROJECT.md) — problem, personas, Faster/Easier/Reliable | **DOCUMENTED**, not validated with real retailers |
| Solution design SD-1..2 | Source design documented | [Architecture](../../ARCHITECTURE.md), [FDE/patterns](DESIGN.md) | **DOCUMENTED**; actual pattern paths require runtime proof |
| Regression unit/API/frontend | Historical CI SHA `224fcb79fe3008e1c6462ed2d83e64a4789de5a3` | [CI run](https://github.com/hungtvb/retailIQ/actions/runs/40721904503): 276 Python + 12 Node tests | **PASS (historical SHA)** |
| Mocked graph and local E2E | Same SHA `224fcb7` | [Quality CI](https://github.com/hungtvb/retailIQ/actions/runs/40721904431): 3 mocked graph tests, 5 E2E groups, 400/400 measured requests | **PASS (historical mocked/local)**, not live provider |
| Demo SD-3 — five full-mode scripted paths | **2026-10-29**, local machine; exact run code SHA not retained alongside report | `python -m scripts.full_e2e`, stock, revenue, top sellers, product RAG, review: **5/5** | **PASS (dated provider-backed scripted set)**; local `data/full_e2e_report.json` is ignored/uncommitted |
| RAGAS | **2026-10-29**, 3 product cases | [RAGAS result JSON](assets/week1_ragas_2026-10-29.json) — faithfulness mean 1.000, relevancy mean 0.729, minimum 0.665 | **PASS (dated tiny set)**, not global reliability |
| LangSmith tracing | **2026-10-29** | [Stock trace](https://smith.langchain.com/o/b2b60b66-94a2-4ec4-9bde-f3659243404f/projects/p/c0a76076-9285-45b3-96e0-aaef05d427e9/r/01a185c2-932a-74fd-9a6a-35e86bb3a267) · [Product trace](https://smith.langchain.com/o/b2b60b66-94a2-4ec4-9bde-f3659243404f/projects/p/c0a76076-9285-45b3-96e0-aaef05d427e9/r/01a185c2-b113-70ef-991c-ea9bba0b002b) | **PASS (dated remote traces)**, private-project access required |
| Cost & ROI | Illustrative model | [DESIGN](DESIGN.md) and `scripts.cost_roi` | **ESTIMATE**, not savings or billed cost |
| Testing/risk SD-4 | Golden cases and RAGAS; UX evidence missing | `tests/test_business_golden_scenarios.py`, `scripts.audit_queries`, [pilot protocol](../../archive/2026-10-30/legacy/23_INTERNAL_SYNTHETIC_BUSINESS_PILOT.md) | **PARTIAL**; broad queries and genuine user task measurement not established |
| Python 3.12 migration baseline | **2026-10-30**, commit `a72ad50024fbf5bd5ed6f31725a2d1785cd00012` | [Python regression run](https://github.com/hungtvb/retailIQ/actions/runs/40996894622) and [local E2E/benchmark](https://github.com/hungtvb/retailIQ/actions/runs/40996894553) both completed successfully | **PASS (dated SHA)**; does not certify commits after `a72ad50` |

### Evidence interpretation: avoid conflicting status

The old **2026-10-28** lesson compliance audit, agent implementation notes, slide guide and traceability sheet say “RAGAS/LangSmith not verified.” Those were valid **earlier snapshots**; the separately recorded **2026-10-29** provider-backed RAGAS/remote trace observations supersede them for that dated scope. The `full_e2e_report.json` booleans `ragas_scores_verified=false` and `langsmith_remote_trace_verified=false` mean that script did **not** perform the separate checks; they do not contradict independent later runs.

Original details: [2026-10-28 compliance](../../archive/2026-10-30/legacy/13_WEEK1_LESSON_COMPLIANCE_AUDIT.md) · [original live summary](../../archive/2026-10-30/legacy/09_Week1_Checklist_and_Evidence.md) · [benchmark](../../archive/2026-10-30/legacy/20_LOCAL_E2E_BENCHMARK_EVIDENCE.md).

### Business and reliability acceptance

Stock: available = on_hand − reserved by location; no fabricated zero for missing rows. Revenue: completed orders in selected month, line discount applied; top sellers by completed units sold, deterministic SKU tie-break. Product knowledge is sourced from documents; never substitute it for inventory. The [14 historical golden scenario IDs](../../archive/2026-10-30/legacy/22_BUSINESS_GOLDEN_SCENARIOS.md) cover period/status exclusions, thresholds, invalid data, ambiguity and exact SKU matching.

An early product retrieval missed AlphaBook at 0.430 versus threshold 0.45; the local demo threshold changed to 0.40 and was retested. This **does not** establish a globally optimal cutoff. The query acceptance audit initially contained predictions for price rankings, arbitrary top-N and contextual stock. The **2026-10-30 Python 3.12 CI** on `e90376be` ran the audit in offline mode and **observed 9 PASS / 11 FAIL / 0 ERROR**. These business-case failures are not pytest failures, and offline results do not establish full-mode LLM quality. Reproduce with `python -m scripts.audit_queries --mode offline` and inspect the CI report artifact for individual cases.

### Gaps, limitations and future work

- **User business value:** no real retailer timing baseline, structured 1–5 ease-of-use comparison or measured ROI. Synthetic pilot is only a rehearsal.
- **Language robustness:** five scripted full-mode cases and three product RAGAS samples cannot cover open-ended questions.
- **Freshness:** no operational maximum-age stock SLA in Week 1; planned for Week 2.
- **Security/actions:** local synthetic data, no production authentication or autonomous orders/pricing; formal approval belongs to later weeks.
- **Cost:** observed token counts in LangSmith are not the same as contracted cloud charges.
- **Current revision:** repeat Python 3.12 regression, full-mode provider tests and updated slide checks. The preserved PPTX still needs verification against **all seven** rubric checkpoints.

## Reproduction and reporting

Follow [RUNBOOK.md](RUNBOOK.md). For every run, capture source SHA, OS, Python, mode (offline / mocked / provider), provider versions, date, inputs, expected/observed outcomes, artifact and limitations. Never count a documentation update alone as execution evidence.

## Documentation maintenance gate

The canonical active Markdown links are checked by `python -m scripts.check_docs_links` in the Python 3.12 regression workflow. Archived historical snapshots are excluded intentionally; this checker requires **a fresh passing CI run on the commit introducing it**. This maintenance check does not certify RAGAS, LangSmith or live-provider execution.

## 2026-10-30 documentation guard and Python 3.12 verification

- **Tested SHA:** `e90376be9b883b8095944461c15bf18747d3e1f3` · GitHub Actions Python **3.12**, [Week 1 regression run 40997220849](https://github.com/hungtvb/retailIQ/actions/runs/40997220849).
- **CI result:** **303 pytest PASS**; link checker validated **11 active Markdown files / 94 local links / 0 errors** (root README, nine core project/Week 1 documents, archive index). This is verified for the specified SHA only.
- **Business query acceptance:** **9 PASS / 11 FAIL / 0 ERROR** in offline mode. The CI workflow intentionally records business coverage gaps without failing the unit-test gate.
- **Remaining limits:** no new provider-backed RAGAS/LangSmith run on the consolidation HEAD, no broad open-ended accuracy certification and no observed user productivity gain. This evidence update itself does not retroactively certify a newer commit.
