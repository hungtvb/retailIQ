# RetailIQ — Testing & Scenario Acceptance

**Document owner:** testing approach, reproducible commands, business/control/safety oracles and scenario coverage. This is **not** the current evidence ledger or a certificate that tests passed on the latest commit. [Capability status and open gates](CAPABILITY_LEDGER.md) is the single owner of requirement acceptance; [dated Week 1 execution records](archive/2026-11-03/week-01/EVIDENCE.md) preserve historical evidence. Week-labelled scenario IDs below are existing test identifiers, not a requirement to organize new source code by course weeks.

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
| Business questions | `python -m scripts.audit_queries --mode offline --strict` | 32 independently checked synthetic business/conversation scenarios (as enumerated in the current script) |
| Workflow behavior | `python -m scripts.audit_workflows --strict` | 19 per-feature scenarios, API + SQLite oracle |
| Real browser | `python -m scripts.smoke_workflow_browser` | Week 1–4 UI, evidence, approval, retry/blocked and conversation follow-ups |
| MCP actual stdio | `python -m scripts.smoke_mcp_stdio` | Real subprocess MCP Inventory + Order calls; verify against SQL, not mock output |
| Adversarial edge cases | `python -m scripts.audit_edge_scenarios --strict` | 14 more HTTP/SQLite checks on ambiguous references and corrupt/missing data |
| Compatibility regression | `python -m pytest -q` | Protect existing contracts; **not** feature acceptance on its own |

Both audits write JSON reports under `data/`; GitHub Actions retains them as
downloadable artifacts. The browser command uses a **disposable seeded database**,
not an existing local user database. It needs Chromium/Chrome and Playwright.
The MCP smoke needs the optional `mcp` and `langchain-mcp-adapters` dependencies.
Its subprocess gets the same isolated fixture via environment variables.

## Running and interpreting evidence

Use a clean synthetic fixture as required by the individual script. Some commands seed disposable databases; running `scripts.seed` directly can replace local synthetic working data, so use the existing runbook and back up customized fixtures. `--strict` fails when the scenario result contains FAIL/ERROR; a historical report may have used non-strict mode. Full-mode query audits may incur provider calls and require explicit `--confirm-live`; do not run them without configured credentials and a recorded model/version.

**Modes:** `offline_synthetic` (reviewed SQLite and deterministic rules), `mocked` (fake model/adapter), `local_mcp_stdio` (real local subprocess transport), and `provider-backed` (actual LLM/embedding/remote trace). Keep these independent in result reporting. A source-freshness tier or static graph node does not prove fresh data or a real agent invocation.

## Manual live LLM acceptance (opt-in; paid provider calls)

**Separate workflow:** [Live LLM Acceptance](../.github/workflows/live-llm.yml). It uses **only** `workflow_dispatch` on `main`: no scheduled, push or pull-request execution; normal offline CI never needs provider credentials.

**One-time GitHub setup (do not send secrets in chat):**

1. Repository **Settings → Environments → New environment**: name it exactly `llm-evaluation`. Restrict deployment branches to `main`; add a required reviewer if your GitHub plan/environment supports it.
2. In that **environment**, configure two secrets: `OPENAI_BASE_URL` (**HTTPS API base**, e.g. Azure OpenAI v1 `https://<resource>.openai.azure.com/openai/v1/`, not `/chat/completions`) and `OPENAI_API_KEY`. Configure optional environment variables `CHAT_MODEL` and `EMBEDDING_MODEL` with actual model/deployment names; leave unset to use the code's defaults. Do not paste values in logs, PRs or this document.
3. Go to **Actions → RetailIQ - Live LLM Acceptance → Run workflow → Branch: main**, select `smoke` first, then `critical` after connectivity works.

| Suite | Execution | Evidence/meaning |
|---|---|---|
| `smoke` | Install full runtime; make **one real chat call and one embedding call** with `scripts.check_openai --live` | Provider credentials and two model endpoints respond. Not a business correctness test. |
| `critical` | Smoke, seed **synthetic** local SQLite, build Chroma with real embeddings, then `audit_queries --mode full --ids SALES-05,CROSS-01,CTX-04,CAT-01,SALES-12,RAG-01 --confirm-live --strict` | Six business cases with actual LLM routing/context/product retrieval, compared to the audit's independent oracles. Failure must fail the job; do not replace with deterministic/fake answers. |
| `uc01` | Real LLM routing through compiled LangGraph `/ask` on **published pinned Fiction SQLite** + exact warehouse policy Markdown; `scripts.verify_uc01_live_release --confirm-live` checks G1 against independent raw SQL/policy hash. Existing real-model **mini-fixture** regression runs separately. No embedding call required. | **G1 live-provider PASS and post-refactor PASS, 2026-11-04:** [pre-refactor run 41776582027](https://github.com/hungtvb/retailIQ/actions/runs/41776582027) on `main@ece87044`, **[post-refactor run 41790444949](https://github.com/hungtvb/retailIQ/actions/runs/41790444949) on `main@32522383`**; downloaded/inspected artifact `retailiq-live-llm-evidence`, `uc01_t02_g1.json`: actual provider, `route_fallback=false`, case/cutoff/warehouse/snapshot/5 units/policy document match real-release SQL oracle, `NEEDS_REVIEW`, no writes. PR-only `--oracle-only` separately uses **FAKE router**, **NO LLM**. G2/G3, RAG, browser, Manager HITL and full UC-01 remain open. |
| `uc01_policy` | **Opt-in paid**, only after T05 code merges on `main`: `scripts.verify_uc01_policy_live --confirm-live` loads pinned real Fiction SQLite/policy, checks the independent G1 SQL oracle, routes one actual LLM G1 case then asks verified same-session Manager-approval and 24h policy questions. Actual model selects exact section + verbatim quote; citation, source SHA, case/cutoff, unchanged disposition/approval and SQL/retrieval/model events are checked. Negative model-quote fixture rejects fabricated evidence without a business write. | **PENDING provider-backed acceptance** until the post-merge manual run and artifact are inspected (including selected quote, usage tokens, latency, expected/observed G1, and source/cutoff). PR CI `--oracle-only` uses an explicitly **FAKE router + quote model, NO LLM** and cannot close T05. Broader 5,003-doc Chroma/hybrid and RAGAS remain open in #27. |

The workflow uses Python 3.12, serialized concurrency and a 30-minute job timeout. It exports a **7-day GitHub Actions artifact** with the strict query report or UC-01 G1 expected/observed oracle (when created) plus non-secret commit/run/mode metadata. A failed setup can legitimately have no query report. GitHub Environment Secrets are scoped to this job; `LANGSMITH_TRACING=false` unless an independent, explicitly approved remote-tracing gate is added.

**Boundary:** These suites cover provider connectivity, synthetic queries and bounded UC-01 G1/policy passage gates only when explicitly dispatched; they do **not** establish the full UC-01 end-to-end outcome. It does **not** run RAGAS, establish LangSmith trace acceptance, test arbitrary natural-language requests, prove live retailer freshness or production security. Track these separately in the [Capability Ledger](CAPABILITY_LEDGER.md) when artifacts can be reviewed.

## Scenario coverage (existing course-labelled IDs)

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

### Historical audit findings (not current PASS claims)

1. `W2-FRESH-MIXED` failed: the freshness calculation used the **newest**
   location timestamp, falsely passing stock with another stale location.
   Corrected to evaluate the oldest timestamp across included locations.
2. `W3-APPROVE` and `W3-REJECT` failed: approval duplicated the manager
   node in the recorded trace and broke the `from` edge. Corrected by updating
   the existing awaiting node, then appending one finalization event.
3. **Chromium E2E** caught a UI bug: the blocked proposal still displayed
   Approve/Reject because author CSS `display:flex` overrode `hidden`.
   The review control is now explicitly `display:none` while hidden.
4. **Actual MCP stdio** caught an adapter bug missed by its mock-based test:
   the LangChain tool result arrived as content blocks, not always a dict.
   The decoder now normalizes supported response shapes *before* validating
   SKU and stock schema; malformed results still fail closed.

Initial run: **16/19 PASS**; after corrections, the strict audit recorded
**19/19 PASS** in GitHub Actions run
https://github.com/hungtvb/retailIQ/actions/runs/40871264052.

A later **historical** CI run reported **20/20 business queries**, **19/19 workflow scenarios**, real **Chromium E2E**, and **MCP Inventory/Order stdio** together:
https://github.com/hungtvb/retailIQ/actions/runs/40872427598. These results apply only to that run and its tested code, not to the present `main`.

## Additional adversarial acceptance (2026-10-29)

A second, independent fixture-based audit was introduced because the initial
**20/20 conversation** and **19/19 workflow** suites left common failure modes
untested. It executes real FastAPI endpoints, isolated seeded databases and
an independent SQL oracle; it does **not** use a simulated chat response.

| Scenario IDs | Required business behavior |
|---|---|
| CHAT-TOP2 / CHAT-TOP3-EN | Return exactly 2/3 ranked SKUs with stock for each |
| CHAT-PRONOUN-TOP3 | "Các sản phẩm đó" refers to prior top-3 September group |
| CHAT-RANK3 | A valid third-place reference resolves the third SKU |
| CHAT-RANK-OUTSIDE / CHAT-RANK-ZERO | Invalid ordinal after top 3 must **ask**, not silently choose top one |
| CHAT-PLURAL-EN | "What about their stock?" returns the ranked group, not only top one |
| CHAT-ISOLATION | References do not leak between conversations |
| CHAT-NAMED-PRONOUN | An explicit product name remains the SKU anchor |
| W4-EMPTY-INVENTORY / W4-ZERO-STOCK | No inventory / all reserved blocks order proposal |
| W2-NULL-TIMESTAMP / W2-FUTURE-TIMESTAMP | Missing timestamps fail closed; future timestamps never count as fresh |
| W3-W4-NEGATIVE-PRICE | Invalid negative price cannot create a pricing or order proposal |

**First adversarial audit:** 10/14 PASS, 4 actual defects:
- Prior top-3 rank 4 (or rank 0) incorrectly fell back to top seller.
- An English plural pronoun incorrectly selected only top seller.
- Corrupted source price `-1 VND` created an approval-ready pricing proposal.

The routing/context resolution now preserves invalid references for
clarification; English plural phrases resolve to the prior ranked group;
`catalog_product` rejects invalid negative, null and non-integer prices
before price/order proposals. Two additional real Chromium conversations
check out-of-range ordinal clarification and plural-reference stock against SQL.

**Historical 2026-10-29 strict run:** 14/14 edge scenarios, 20/20 business scenarios, 19/19 workflow scenarios, and browser/MCP integration checks reported PASS in https://github.com/hungtvb/retailIQ/actions/runs/40878317768. **Do not treat this as latest/current acceptance:** a separately documented 2026-10-30 offline query audit reported **9 PASS / 11 FAIL / 0 ERROR** on its recorded commit; see [dated evidence](archive/2026-11-03/week-01/EVIDENCE.md). Re-run the selected suite on the target SHA and inspect each failed case before updating acceptance status.

Each suite remains a bounded sample of user behavior. All three are *offline
synthetic acceptance*, except the separately verified **actual local MCP stdio**
transport. No evidence here justifies marking RAGAS, LangSmith live, Langfuse,
DeepEval, autonomous A2A, or production authorization as complete.

## Reporting and acceptance ownership

For every reported result, record the **test SHA, run date, environment, execution mode, command and input, independent oracle, pass/fail counts, artifact/trace reference and limitations**. A green unit-test suite, a screenshot of the graph, or an API HTTP 200 response alone does not establish business correctness.

- **Scenario definitions and reproduction:** this document and existing test scripts.
- **Current capability status and missing gates:** [capability acceptance ledger](CAPABILITY_LEDGER.md). Do not duplicate a live status table here.
- **Historical provider/RAGAS/LangSmith evidence:** [Week 1 evidence](archive/2026-11-03/week-01/EVIDENCE.md); prior dated provider results are not present-commit acceptance.
- **Run artifacts:** CI artifacts or access-controlled external storage. Keep generated reports, screenshots and traces outside Git (do not delete existing historical artifacts without preserving them).

A locally verified MCP stdio call is not a hosted integration; model-free simulated approvals are not authenticated HITL; provider-backed product RAG is distinct from offline lexical retrieval. Do not label one mode as another.

## Harness H0 — baseline protocol and proposed acceptance (Review 03 / issue #23)

**Status: PLAN / NOT EXECUTED for this change.** This is the reproducible protocol for the [Harness H0 design](DESIGN.md#harness-h0--bounded-execution-and-controlled-planning-review-03-proposed-2026-11-07). Existing historical CI successes must not be presented as new harness acceptance. Use `main@dc8eb1ac692461d3c94bf27f8f000658e353d02d` as the read-only design baseline; code PRs must record their own SHA. Open PR #63 changes routing, answer integrity and audit checks, so rebase and remeasure **after** its integration rather than copying its results into current `main`.

### Baseline measurement method (H0-B)

1. Record exact Git SHA, model/deployment (or `none`), execution mode, fixture/source SHA and request/session IDs. Keep generated results, JSONL traces and reports **outside Git**.
2. Use disposable synthetic fixtures for legacy paths. For Fiction UC-01 use only the published, pinned release and independent SQL/policy oracle; no EL/FR fallback and no fabricated available stock.
3. For every scenario capture: actual route/agent/capability sequence, sanitized typed tool arguments and verified outputs, source/evidence IDs, clarification/stop reason, outcome vs independent oracle, logical model/tool calls, counted retries, wall-clock time and tokens **only if the provider reports them**. Do not convert estimates into measured token usage.
4. Run each deterministic/mocked scenario at least once; repeat latency comparisons with enough identical runs to disclose sample count, median and p95 rather than extrapolating from one sample. Actual provider calls are manual/opt-in via the existing live gate, never implicitly triggered by this docs PR. Treat model/SDK-internal retry counts as **unknown** unless instrumented at the right layer.
5. Start from the existing targeted no-provider commands below, then add harness-specific tests in implementation PRs. Passing a fixture test does not establish real LLM routing accuracy. All answers involving business facts require independent domain evidence.

```bash
python -m pytest -q tests/test_orchestration_hardening.py tests/test_harness_fixes.py tests/test_agent_execution_instrumentation.py tests/test_full_mode_dispatch.py
python -m scripts.audit_queries --mode offline --strict
python -m scripts.audit_edge_scenarios --strict
```

Existing [main CI #41858108933](https://github.com/hungtvb/retailIQ/actions/runs/41858108933) is a historical `success` on the baseline SHA, **not** a harness design test. The [#63 branch Python CI #41978086402](https://github.com/hungtvb/retailIQ/actions/runs/41978086402) is on a **different, unmerged** SHA. No new harness baseline or paid-provider suite was executed as part of this design proposal.

### Golden and negative scenario matrix (H0-S; all pending)

| ID | Request / fault injection | Independent acceptance oracle | Minimum mode |
|---|---|---|---|
| H0-01 | Clear single-SKU inventory query | Exactly one authorized reviewed inventory read; exact SKU/location/source, no unnecessary planner or model calls on deterministic fast path | offline_synthetic + mocked graph |
| H0-02 | Top-5 ranked sales for period P then inspect stock | Five exact source-ranked product identities; stock uses those IDs, retains ranking period and records inventory freshness separately; no missing capability | mocked graph + independent SQL |
| H0-03 | Rank #2 follow-up after the ranking changes in the DB | Resolve the previously **committed** displayed SKU, or clarify if original evidence absent; never silently recalculate the rank | session + independent SQL |
| H0-04 | Price + stock + warranty; separate September rank and October revenue | Plan covers all requested supported dimensions with original/inherited scopes; cannot substitute whole-store totals or omit one source | mocked graph + independent SQL/RAG |
| H0-05 | UC-01 G1 with real CASE-ID; followed by order details | Same source SHA/case/cutoff/policy and exact evidence lineage; validated result, no operational write; MCP is real stdio only when explicitly tested | real Fiction oracle + local_mcp_stdio; provider-backed optional |
| H0-06 | Unknown SKU/warehouse, ambiguous period or ranking | Targeted CLARIFY, no global/unscoped fallback, no unsupported business conclusion | offline_synthetic + mocked graph |
| H0-07 | Model proposes unknown tool, arbitrary SQL, unbound output or a dependency cycle | Trusted plan validator DENIES/CLARIFIES before any tool execution; no model-granted permission | mocked |
| H0-08 | Task limit/fan-out/model/tool-call or deadline budget exceeded | STOPPED with stable reason; bounded observed calls, no unverified final business answer; a cooperative timeout is **not** reported as forced cancellation | mocked + time-controlled |
| H0-09 | Duplicate read invocation, transient `database is locked`, non-transient corruption | Deduplicate only when safe/equivalent; transient read bounded at reviewed attempts, corrupt/permission/contract errors never retried | mocked + SQLite fault |
| H0-10 | Wrong SKU/source version, stale/undated observation, conflicting applicable policy | Domain evidence gate blocks unsupported decision; verified partial facts may appear with explicit limitations/reason codes | Fiction oracle + mocked |
| H0-11 | Failed session commit after graph verification, lost SSE client, checkpoint resume, then new question | `run_verified` may exist, but no `turn_committed`/`run_completed` or successful final when persistence fails; no stale/uncommitted context leak, unsafe approval retry or cross-session reuse; observed execution retains request ID | API/session/SSE mocked |
| H0-12 | Unauthorized user/session/cross-location request and same-browser identity switch | Enforced server-side owner/location scope; denied before read or HITL; **requires merged T06** and authenticated Chromium gate, not a fake role label | authenticated browser after T06 |
| H0-13 | Injected document/tool text attempts to change permissions or plan | Untrusted text cannot mutate tool allowlist, owner, business source/time/coverage or verified outcome | mocked retrieval + tool result |
| H0-14 | Events include a proposed node never executed; telemetry sink unavailable | No phantom execution edge; logging failure non-fatal yet counted; only verified final answer committed and displayed | API/SSE + mocked |

**Acceptance threshold:** every scenario required by a code slice must compare expected vs observed **business facts, control flow, tool arguments, evidence refs and side effects**, not just regex matches on the final answer. The first design PR may mark none of H0-S as PASS. A source-backed regression or denied plan with missing event/reason fails the harness gate even if HTTP returns 200. Mark ambiguous/unsupported outcomes as gaps; never auto-skip.

### Per-slice release gates

- **H1-A:** cases H0-01, 05, 06, 08–11, 14 + existing graph/SSE/session tests; distinguish logical call count, real provider attempts, deadline observation and worker cancellation. Zero silent extra business writes.
- **H1-B:** cases H0-02–04, 07, 10, 12–13 + scoped auth/context/evidence fixtures after dependencies are merged. Test plan coverage, scope preservation and output lineage on the actual selected tools.
- **H1-C:** add multilingual paraphrases, rule/model disagreements, source loss between tasks, bounded repair and provider-backed comparisons; use an independent oracle and a **manual** paid gate only when relevant. Record false routing, omission, clarification, cost and latency relative to H0.
- **H2:** **no gate scheduled** until a real scenario demonstrates the fixed plan/DAG cannot suffice. If adopted, test no-progress/duplicate detection and additional model/tool spend against Phase 1.

**Reporting template:** `commit | scenario | mode | input/fixture/source SHA | expected | observed | route/task/tool trace | tokens (reported/unknown) | elapsed | outcome/stop_reason | artifact location | remaining gaps`. Owner #23 and affected UC Issues receive actual test links after execution; update `CAPABILITY_LEDGER.md` only when acceptance evidence changes.
