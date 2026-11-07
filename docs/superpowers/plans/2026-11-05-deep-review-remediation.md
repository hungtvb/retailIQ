# Deep-Review Remediation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **Codex execution note:** Tasks 1–3 are independent and may run in parallel with disjoint file scopes. Do not commit; leave changes in the working tree for the Lead to review and commit. Task 4 runs after 1–3. Task 5 is the Lead gate.
>
> **Status (2026-11-05):** Tasks 1–4 implemented and committed on `fix/deep-review-remediation` (`a9d98f7` domain, `ba20477` retrieval evidence, `cc4b6a9` portability/CI, `7126554` docs). Task 5 evidence: full pytest **527 passed / 1 pre-existing Windows-symlink failure / 2 skipped**; strict audits (`audit_queries`, `audit_workflows`, `audit_edge_scenarios`, `audit_freshness`, `report_source_reliability`) all exit 0; `check_docs_links` 0 errors. Deferred register unchanged (no Important/Minor backlog items fixed).

**Goal:** Fix the Critical findings from the 2026-11-05 deep review (wrong KPI period/scope, ungrounded answers labelled as verified, weak evidence gates, Windows-broken live gates, stale docs) on branch `fix/deep-review-remediation`, without touching paid-provider behavior.

**Architecture:** Keep existing module boundaries (domain math in `retailiq/domain`, HTTP in `retailiq/api`, scripts as evidence gates). Fixes are fail-closed corrections: ambiguous period/scope asks for clarification instead of returning a plausible wrong aggregate; conversational fallback is labelled as such; evidence scripts assert against independent expectations; documented gates exit 0 when business checks pass.

**Tech Stack:** Python 3.12, pytest, FastAPI, LangGraph, Chroma, SQLite, GitHub Actions YAML, vanilla JS/React untouched.

**Spec (review evidence):**
- `D:\CODE\retailiq-review-artifacts\DEEP_CODE_REVIEW_2026-11-05.md` (C1–C6, Important list)
- `D:\CODE\retailiq-review-artifacts\verify-live\00-VERIFICATION-ADDENDUM.md` (V1–V4 new findings)
- Area reports under `D:\CODE\retailiq-review-artifacts\reviews\`

## Global Constraints

- Branch: `fix/deep-review-remediation` (already created from `dc8eb1a`; never switch/checkout).
- Do **not** commit, amend, rebase, push, or open a PR. The Lead commits per task after review.
- Do **not** make paid provider calls (`OPENAI_*`, embeddings, RAGAS, LangSmith export). All new tests must run offline against temp DBs.
- Do **not** edit files outside your task's File list. If a fix requires another file, stop and report instead.
- Keep public signatures stable unless a task says otherwise. Python 3.12 syntax; no new dependencies.
- Every behavior change gets a failing test first (TDD red → green), then the minimal implementation.
- Run targeted tests only: `.\.venv312\Scripts\python.exe -m pytest -q -p no:cacheprovider <files>`. Do not run the full suite.
- Windows host: use `pathlib`/`tempfile` correctly; never write to `data/*.sqlite3` or other tracked/ignored repo DBs.
- Update `docs/` only in Task 4; Tasks 1–3 report required doc changes instead of editing docs.
- Vietnamese/English wording in answers must stay natural; no mojibake (files are UTF-8).

## Review Focus (inputs most likely to bite a user, each pinned to a task)

1. **Temporal wording that is not a month** ("may we expect", "previous quarter", accent-less Vietnamese) must clarify, never answer another month — Task 1.
2. **A named but unresolved subject** (partial product name, unknown SKU, city) must clarify, never return the store total — Task 1.
3. **A data question classified as chit-chat** must not be answered with invented numbers under a "verified SQL/RAG" label — Task 1.
4. **A retrieval audit** must fail on the wrong source document, not merely on an empty one — Task 2.
5. **A documented live gate** must exit 0 when its business checks pass on Windows — Task 3.
6. **A PR without magic title words** must still run real-release verification (or be reported NOT VERIFIED), never silently green — Task 3.

---

## File Structure (what each task owns)

| Task | Files | Responsibility |
|---|---|---|
| 1 | `retailiq/domain/analytics.py`, `retailiq/domain/revenue_plan.py`, `retailiq/queries.py`, `retailiq/orchestration/week1_graph.py`, `tests/test_answer_integrity.py` (new), `tests/test_retailiq_reply.py` (extend) | Fail-closed period/scope + honest conversational label |
| 2 | `scripts/audit_queries.py`, `scripts/eval_retrieval.py`, `tests/test_retrieval_evidence.py` (new) | Evidence gates must discriminate |
| 3 | `scripts/verify_uc01_live_release.py`, `scripts/verify_uc01_policy_live.py`, `scripts/smoke_mcp_stdio.py`, `.github/workflows/ci.yml`, `tests/test_evidence_portability.py` (new) | Gates portable + actually scheduled |
| 4 | `README.md`, `docs/*.md`, `docs/wiki/*.md`, `docs/implementation/UC-01-backorder.md` (only status lines) | Reconcile claims with code/evidence |
| 5 | none | Lead verification and commits |

---

## Task 1: Answer integrity — period, revenue scope, conversational labelling

**Files:**
- Modify: `retailiq/domain/analytics.py` (`requested_month`, + `PERIOD_HINT_RE`/`_looks_period_like`)
- Modify: `retailiq/domain/revenue_plan.py`
- Modify: `retailiq/queries.py` (`intent`, `product_sku` callers, `do()` revenue/top/stock paths)
- Modify: `retailiq/orchestration/week1_graph.py` (`retailiq (general) node` / payload `mode` + `limitations`)
- Create: `tests/test_answer_integrity.py`
- Extend: `tests/test_retailiq_reply.py` (keep existing passing expectations)

**Interfaces:**
- Produces: `requested_month(question: str) -> str` unchanged signature; raises `retailiq.domain.analytics.DomainDataError` when a period-looking phrase cannot be resolved.
- Produces: `retailiq.domain.revenue_plan.build_revenue_plan(question, *, resolve_sku, is_ranked, ranked_position, known_locations=None)` — new optional `known_locations: Callable[[], list[str]] | None`.
- Produces: `retailiq.queries.resolve_known_locations() -> list[str]` (reads `SELECT DISTINCT location FROM inventory` through `retailiq.domain.analytics.inventory_locations`).
- Produces: response payload `mode` is `'LangGraph conversational (no business evidence)'` for the `retailiq` general node; `limitations` includes `'No verified business data used'`.

- [ ] **Step 1: Write the failing tests** in `tests/test_answer_integrity.py` (offline, temp seeded DB via `scripts.seed.seed`):
  - `test_modal_may_is_not_a_month`: `requested_month("What revenue may we expect in October 2026?") == "2026-10"`.
  - `test_unparsed_period_clarifies`: for `"previous quarter"`, `"Q3 2026"`, `"quý 3 năm 2026"`, `"tháng vừa rồi"` — `do(q, 'revenue')` returns `query_plan.scope == 'clarify'` and answer contains no `'563,742,000'` store total.
  - `test_unknown_sku_scope_clarifies`: `"Doanh thu của SKU EL-999 trong tháng 10?"` → clarify, no store total.
  - `test_partial_product_name_scope_clarifies`: `"Revenue for AlphaBook in October 2026?"` → clarify (full name is "AlphaBook Pro 14").
  - `test_location_scope_clarifies`: `"Doanh thu tháng 10 tại Đà Nẵng?"` and `"Doanh thu tháng 10 tại Hà Nội?"` → clarify.
  - `test_plain_store_revenue_still_answered`: `"What is our revenue in October 2026?"` → non-clarify store total.
  - `test_data_question_routing`: `intent("What were our sales last month?") == "revenue"`, `intent("Top 3 sellers") == "top"`, `intent("How many orders did we ship in October?") in {"revenue","top"}` (pick one, assert exact).
  - `test_general_answer_is_labelled_unverified`: with a fake chat model returning `"Sales were 999"` for `"What were our sales last month?"`, the payload `mode` is not `'LangGraph Multi-Agent + SQL / Chroma RAG'`; for `"What can you help me with?"`, `mode == 'LangGraph conversational (no business evidence)'` and `'No verified business data used' in limitations`.

- [ ] **Step 2: Run to confirm red**
  Run: `.\.venv312\Scripts\python.exe -m pytest -q -p no:cacheprovider tests/test_answer_integrity.py`
  Expected: failures for the new cases, not import errors.

- [ ] **Step 3: Implement**
  - `analytics.requested_month`: month regex must not match a bare modal `"may"`; require `in <month>`, `<month> <year>`, or a Vietnamese `tháng <n>` form. Add `_looks_period_like(text)` for `quarter|quý|q[1-4]|year|năm|previous|last|next|trước|sau|month|tháng`; if no explicit month resolves and `_looks_period_like` is true → `raise DomainDataError('Unrecognized sales period')`.
  - `revenue_plan.build_revenue_plan`: when a subject marker resolves to nothing (unknown `XX-999` SKU, product-ish name after `of/for/của/sản phẩm`, or a location matched by `known_locations()`), return `RevenuePlan(period, 'clarify', reason=...)`. Keep `scope='store'` only for questions with no subject marker.
  - `queries.do`: wrap period resolution + plan building in `try/except DomainDataError` for `revenue`, `top`, `stock` multi-SKU paths; return a clarification answer (no records, `query_plan.scope='clarify'` for revenue) instead of propagating.
  - `queries.intent`: add sales synonyms (`sales`, `sold`, `orders`, `doanh số`, `đơn hàng`, `top N seller(s)`), normalize Vietnamese diacritics for matching.
  - `week1_graph`: in the `retailiq` node path, ensure the payload `mode` is the conversational label and append the limitation; never use the SQL/RAG label when `active_agent == 'retailiq'` and no `records`/`contexts`.

- [ ] **Step 4: Run green + existing targeted tests**
  Run: `.\.venv312\Scripts\python.exe -m pytest -q -p no:cacheprovider tests/test_answer_integrity.py tests/test_retailiq_reply.py tests/test_ranked_product_revenue.py tests/test_inventory_sales_hardening.py`
  Expected: all pass. If an existing expectation conflicts with the new fail-closed behavior, update it only where the old behavior was the bug; note the change in your report.

- [ ] **Step 5: Commit (Lead only — do not commit)**
  ```bash
  git add retailiq/domain/analytics.py retailiq/domain/revenue_plan.py retailiq/queries.py \
          retailiq/orchestration/week1_graph.py tests/test_answer_integrity.py tests/test_retailiq_reply.py
  git commit -m "fix(domain): fail closed on ambiguous period and revenue scope"
  ```

## Task 2: Evidence gates — retrieval audit and evaluation must discriminate

**Files:**
- Modify: `scripts/audit_queries.py` (`Case`, `CASES` RAG rows, `assess` `product_sources`)
- Modify: `scripts/eval_retrieval.py` (`CASES`, `evaluate_source_retrieval`, dataset version)
- Create: `tests/test_retrieval_evidence.py` (no provider calls)

**Interfaces:**
- Produces: `Case.expected_source: str = ''`; `assess` returns `ok=False` when retrieved contexts do not include the expected source.
- Produces: `evaluate_source_retrieval(cases, search, *, k=3)` supports `expected_source=None` abstention cases (`hit_at_k = (contexts == [])`).

- [ ] **Step 1: Failing tests** in `tests/test_retrieval_evidence.py`:
  - `test_audit_rejects_wrong_source`: build a fake `Case('RAG-01', ..., check='product_sources', expected_source='data/product_docs/EL-003.md')`; response `{'intent':'product','answer':'unrelated nonsense','contexts':[{'source':'data/product_docs/EL-001.md'}]}` → `assess(...)[0] is False`; with EL-003 → `True`.
  - `test_eval_query_set_has_no_title_leakage`: for each case in `eval_retrieval.CASES` with an expected source, the query must not contain the expected document's first-line title verbatim (parse the doc's first `#` heading); fail listing leaked ids.
  - `test_eval_has_distractors_and_abstention`: `len(CASES) >= 12`, at least 1 case with `expected_source=None`, at least 3 distinct expected sources, dataset string ends with `v2`.
  - `test_abstention_scores_only_on_empty_context`: `evaluate_source_retrieval((( 'X','q',None),), lambda q,k: [], k=3)['summary']['source_recall_at_k'] == 1.0`; same with one context → `0.0`.

- [ ] **Step 2: Red** — run the file; expect failures.

- [ ] **Step 3: Implement**
  - `audit_queries`: add `expected_source` to `Case` (default `''`); set `RAG-01` expected `data/product_docs/EL-003.md`; in `product_sources` require `any(c.get('source','').endswith(case.expected_source) for c in contexts)`; update the returned `expected` dict to include `expected_source`.
  - `eval_retrieval`: rewrite `CASES` as de-titled, natural questions (no product H1 verbatim), add ≥2 distractor questions whose expected source is a knowledge doc (`data/knowledge/...`), ≥1 abstention case (`expected_source=None`, e.g. `"What is our current stock level in the Hanoi warehouse?"`), bump dataset to `synthetic_product_docs_heldout_queries_v2`; extend aggregation for abstention; keep `--strict` semantics (abstention counts as hit only when no context).

- [ ] **Step 4: Green** — run the new test file; then `python -m scripts.check_docs_links` only if docs were touched (they are not).

- [ ] **Step 5: Commit (Lead only)**
  ```bash
  git add scripts/audit_queries.py scripts/eval_retrieval.py tests/test_retrieval_evidence.py
  git commit -m "fix(evidence): make retrieval audit and evaluation discriminate"
  ```

## Task 3: Evidence portability and CI gating

**Files:**
- Modify: `scripts/verify_uc01_live_release.py`, `scripts/verify_uc01_policy_live.py`, `scripts/smoke_mcp_stdio.py` (cleanup only)
- Modify: `.github/workflows/ci.yml` (gate triggers)
- Create: `tests/test_evidence_portability.py`

**Interfaces:**
- Produces: temp directories are created with `ignore_cleanup_errors=True` (or an explicit `_safe_tempdir()` helper) so an open `events.jsonl` cannot turn PASS into exit 1 on Windows.
- Produces: CI jobs `fiction-t04-release` / `fiction-t02-oracle` trigger on `pull_request` **paths** (not title substrings), on a weekly `schedule`, and on `workflow_dispatch`; the paid G1 job remains PR/manual.

- [ ] **Step 1: Failing tests** in `tests/test_evidence_portability.py`:
  - `test_safe_tempdir_survives_open_file`: open a file inside `retailiq_script_helpers.safe_tempdir()` context on Windows; on `__exit__` it must not raise.
  - `test_ci_has_no_pr_title_gating`: parse `.github/workflows/ci.yml` with `yaml.safe_load`; assert no job `if:` contains `github.event.pull_request.title`; assert a `schedule` trigger exists; assert the fiction jobs have `if:` referencing `github.event_name`/`paths` (or are unconditional) — not title text.
  - `test_ci_fiction_jobs_are_path_scoped`: jobs `fiction-t04-release` and `fiction-t02-oracle` have `paths:`-based triggers in the `push`/`pull_request` top-level filters or a job-level guard that can run on `main`/schedule.
  - `test_verify_scripts_use_safe_tempdir`: source-scan `scripts/verify_uc01_live_release.py` and `..._policy_live.py` for `TemporaryDirectory(` followed within 300 chars by `ignore_cleanup_errors=True` (or the helper call).

- [ ] **Step 2: Red** (the tempdir helper does not exist yet).

- [ ] **Step 3: Implement**
  - Add `safe_tempdir(**kwargs)` helper (place in `scripts/_evidence_io.py` if a new module is needed; otherwise module-level in each script — prefer one shared helper) wrapping `tempfile.TemporaryDirectory(..., ignore_cleanup_errors=True)`.
  - Replace the `with tempfile.TemporaryDirectory(...)` calls in the three scripts; verify the no-write hash assertion still runs after business checks.
  - `ci.yml`: remove PR-title `if:` conditions; run `fiction-t04-release` and `fiction-t02-oracle` on `pull_request` with `paths:` for Fiction-relevant files, on `schedule` (weekly cron), and `workflow_dispatch`; keep the paid provider job manual/PR-scoped; add `retry` wrapper to the LFS pull (`for i in 1 2 3; do ... && break || sleep 10; done`) and `permissions: contents: read` + `timeout-minutes` on `python-tests`.

- [ ] **Step 4: Green** — run the new tests; validate YAML:
  `.\.venv312\Scripts\python.exe -c "import yaml,pathlib; yaml.safe_load(pathlib.Path('.github/workflows/ci.yml').read_text(encoding='utf8'))"`.

- [ ] **Step 5: Commit (Lead only)**
  ```bash
  git add scripts/verify_uc01_live_release.py scripts/verify_uc01_policy_live.py scripts/smoke_mcp_stdio.py \
          scripts/_evidence_io.py .github/workflows/ci.yml tests/test_evidence_portability.py
  git commit -m "fix(evidence): portable temp dirs and non-title CI gates"
  ```

## Task 4: Documentation reconciliation (after Tasks 1–3)

**Files:** `README.md:41`, `docs/PROJECT.md:9`, `docs/DATA_API.md:3,11,162` (status lines), `docs/SCENARIO_ACCEPTANCE.md:57`, `docs/ARCHITECTURE.md:3`, `docs/DESIGN.md:3,69-71`, `docs/FICTION_RUNTIME.md:45`, `docs/CAPABILITY_LEDGER.md` (T05 row + W1-04 note + W2-05 status + deployment note), `docs/wiki/context-and-memory.md:26-27`.

**Rules:** one claim owner per fact; mark status with the ledger legend; no new docs; no restating code.

- [ ] **Step 1:** Update status lines so code, ledger and docs agree: Fiction is wired for the bounded CASE-ID `/ask` path; T04/T05 merged with their scoped evidence; `uc01_policy` T05 status consistent between `SCENARIO_ACCEPTANCE` and `UC-01-backorder`; LangSmith W1-04 = "verified locally for `dc8eb1a`, CI does not trace"; W2-05 = "provider-backed measurement exists but query set leaked titles; not quality evidence until v2 run"; deployment note "single-process (`workers=1`) only".
- [ ] **Step 2:** Add the T05 row to `CAPABILITY_LEDGER.md` with implementation paths and scoped evidence links; reference the v2 retrieval run requirement.
- [ ] **Step 3:** Verify links: `.\.venv312\Scripts\python.exe -m scripts.check_docs_links` → exit 0.
- [ ] **Step 4:** Commit (Lead only): `docs: reconcile status with merged implementation and verification evidence`.

## Task 5: Lead gate (no file changes)

- [ ] Full suite: `.\.venv312\Scripts\python.exe -m pytest -q -rs` with `RETAILIQ_REQUIRE_LANGGRAPH=true`.
- [ ] Strict audits: `python -m scripts.audit_queries --mode offline --strict`, `audit_workflows --strict`, `audit_edge_scenarios --strict`, `audit_freshness --strict`, `report_source_reliability --strict`.
- [ ] `python -m scripts.check_docs_links`.
- [ ] `git status` clean after commits; `git log --oneline main..HEAD` reviewed; no paid calls made by any task.

---

## Deferred Register (NOT in this plan — do not fix silently)

| ID | Finding | Why deferred |
|---|---|---|
| I9 | 20k answer limit → misleading 503 | needs API error-taxonomy design |
| I10 | actionable failures masked as 503/`execution_failed` | same design; pairs with I9 |
| F1–F7 | multi-worker unsafe (session/SSE/JSONL/schema/index) | needs SQLite-based locking design; docs note only in Task 4 |
| I15 | `vector_search` skips source-hash check | design decision on comparison arm |
| I16 | unpinned dependencies/lockfiles | separate dependency policy PR |
| I21–I25 | MCP per-call re-verification; test blind spots; minors | backlog, low user impact |
| C-minors | ~65 minor findings | backlog |

## Verification Commands (copy-paste)

```powershell
# task 1
.\.venv312\Scripts\python.exe -m pytest -q -p no:cacheprovider tests/test_answer_integrity.py tests/test_retailiq_reply.py tests/test_ranked_product_revenue.py tests/test_inventory_sales_hardening.py
# task 2
.\.venv312\Scripts\python.exe -m pytest -q -p no:cacheprovider tests/test_retrieval_evidence.py
# task 3
.\.venv312\Scripts\python.exe -m pytest -q -p no:cacheprovider tests/test_evidence_portability.py
# task 5
$env:RETAILIQ_REQUIRE_LANGGRAPH='true'; .\.venv312\Scripts\python.exe -m pytest -q -rs
```
