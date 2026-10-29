# RetailIQ — Behavioral Acceptance Matrix (Four Weeks)

**Scope:** local deterministic teaching workflows; this is an evidence ledger, not a
claim of production readiness or completion of every AI Flezi requirement.

## Acceptance principle

A code path, a UI node, or a passing unit test **does not prove a business scenario works**.

- Business truth: compare HTTP output and reports with independent read-only SQLite
  queries; check key SKU, quantities, prices, completed-order periods and locations.
- Control truth: assert the *recorded* node status and exact directed handoff edges,
  including retry and manager gate (not merely the existence of node definitions).
- Safety truth: snapshot **products, inventory, orders, order_lines** before and
  after all proposal/approval paths. No unexpected business mutation is allowed.
- UX truth: drive the actual FastAPI UI through Chromium, including failure cases.
- Provenance truth: distinguish local reads, preflight calculations, mock tool
  adapters, verified MCP transport, and real model calls.

## Runnable acceptance

| Gate | Command | Purpose |
|---|---|---|
| Business questions | `python -m scripts.audit_queries --mode offline --strict` | 20 independent SQL-checked conversation scenarios |
| Workflow behavior | `python -m scripts.audit_workflows --strict` | 19 per-feature scenarios, API + SQLite oracle |
| Real browser | `python -m scripts.smoke_workflow_browser` | Week 1–4 UI, evidence, approval, retry/blocked and conversation follow-ups |
| Compatibility regression | `python -m pytest -q` | Protect existing contracts; **not** feature acceptance on its own |

Both audits write JSON reports under `data/`; GitHub Actions retains them as
downloadable artifacts. The browser command uses a **disposable seeded database**,
not an existing local user database. It needs Chromium/Chrome and Playwright.

## Scenario coverage by week

| Scenario IDs | Observed behavior & independent oracle | Evidence mode |
|---|---|---|
| W1-REPORT-ORACLE | Top-five completed-order SKU/unit report matches SQL; does not claim live LangGraph | Offline SQL |
| W2-SEMANTICS | Stock/revenue definitions, measurement units, four freshness targets explicitly not guaranteed | Contract |
| W2-LOCAL-STOCK | SKU quantities match DB; local adapter does not claim MCP transport | Offline SQL |
| W2-FRESH-ALL / W2-FRESH-MIXED | All locations fresh passes; **one stale location makes aggregate stock stale** | Controlled timestamps |
| W2-MCP-DRIFT | Deliberately mismatched mock MCP result fails closed | Mocked adapter only |
| W3-SCOPE | Simulated analyst location versus manager-all-locations matches SQL | Mock role + SQL |
| W3-PRICE-GATE | 5% proposal arithmetic correct, pending approval, price unchanged | Offline SQL |
| W3-APPROVE / W3-REJECT | Unauthorized simulated role denied; valid one-shot review; directed trace consistent; no business writes | Mock manager |
| W3-ALERT-19 / W3-ALERT-20 | Threshold boundary and no notification side effect | Controlled stock |
| W4-SINGLE-LOCATION / W4-EXACT-BOUNDARY | Stock sufficient; source-based price and allocation; no extra replan | Offline SQL |
| W4-SPLIT-RETRY | Exactly 20 units allocated as 8+8+4; one feedback/replan; result verified | Controlled stock |
| W4-INSUFFICIENT | Total stock below quantity blocks review and finalization | Controlled stock |
| W4-FIVE-ROLES-LINEAGE | Five named specialist **roles** and reference tool/data-source contract | Deterministic simulation |
| W4-INVALID-INPUT | Wrong SKU, quantity, actor and scenario rejected | HTTP validation |
| CROSS-NO-BUSINESS-WRITE | All five scenarios leave four operational tables byte-logically unchanged | SQLite snapshots |

An additional 20-scenario natural-language audit covers product extremes,
cross-domain top-seller stock, previous-month context and document retrieval
presence. A retrieved document is **not** automatically a valid RAGAS score.

### Faults actually caught by this audit

1. `W2-FRESH-MIXED` failed: the freshness calculation used the **newest**
   location timestamp, falsely passing stock with another stale location.
   Corrected to evaluate the oldest timestamp across included locations.
2. `W3-APPROVE` and `W3-REJECT` failed: approval duplicated the manager
   node in the recorded trace and broke the `from` edge. Corrected by updating
   the existing awaiting node, then appending one finalization event.

Initial run: **16/19 PASS**; after corrections, the strict audit recorded
**19/19 PASS** in GitHub Actions run
https://github.com/hungtvb/retailIQ/actions/runs/40871264052.

## Required course capability status (do not conflate)

| Course capability | Evidence position |
|---|---|
| Week 1 SQL, local chat follow-ups, browser UI | **Offline scenario verified** |
| Week 1 LangGraph live + actual LLM tool traces | **Not verified by offline audit** |
| Week 1 RAGAS / LangSmith reports | **No live evidence gate passed here** |
| Week 2 semantic metrics and freshness checks | **Local behavior verified** |
| Week 2 MCP Inventory/Order stdio handshake | **Optional implementation present; real transport not E2E verified** |
| Week 2 long-term memory, hybrid retrieval and reranking quality | **Not demonstrated by these scenarios** |
| Week 3 manager approval, KPI threshold, location filtering | **Mock behavior verified; NOT real RBAC or notification** |
| Week 3 Langfuse / DeepEval / security report | **Not verified by these scenarios** |
| Week 4 five specialist roles, allocation, verification, proposal | **Deterministic local behavior verified** |
| Week 4 autonomous multi-agent A2A and business write | **NOT implemented/verified as production behavior** |

**Next decision:** prioritize any course-mandatory missing *live* evidence
before adding more agents, infrastructure or UI polish. No feature should be
marked **PASS** without a reproducing scenario and corresponding trace.
