# UC-01 T06 Authenticated Manager HITL Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** An authenticated Analyst submits a verified historical UC-01 backorder proposal; an authenticated Manager records exactly one local approve/reject decision without viewing the Analyst conversation or modifying Fiction operations.

**Architecture:** Reuse FastAPI, existing application SQLite and read-only UC-01 domain verification. Backend-created auth/ownership context protects all business endpoints and SSE; the same SQLite database persists immutable, source-bound proposals and atomic decisions. **No new Agent, HITL LangGraph or approval microservice.**

**Tech Stack:** Python 3.12, FastAPI `>=0.110,<1`, SQLite, `pwdlib[argon2]` (verify version before install), pytest/httpx, React 19.2.0, TypeScript 5.9.3, Vite 6.3.6.

**Spec:** `docs/implementation/UC-01-backorder.md` §10, **reviewed/merged `main@8f5ee7858ae1510de4ab4a3da76448ed11a771af`**, [design PR #59](https://github.com/hungtvb/retailIQ/pull/59). Owner [#29](https://github.com/hungtvb/retailIQ/issues/29), parent [#34](https://github.com/hungtvb/retailIQ/issues/34). This task plan is a **proposal**, not accepted implementation.

## Global constraints

- Exactly two business roles: `analyst` and `manager`; CLI-only provisioning and no default password; local loopback-only host and same-origin cookie auth. No JWT/SSO/admin UI or credentials in Git.
- `main@8f5ee78` is the design baseline; get current `AGENTS.md` and code/versions on the actual implementation branch **before work**. No commits to main. Branch isolation, TDD, PR and final review required.
- Use existing `RETAILIQ_CHAT_DB` (default `data/chat_sessions.sqlite3`) for users, auth sessions, conversation owners and proposal decisions. **Fiction SQLite remains read-only; no transfer/order/stock mutation**.
- Original verified UC-01 case/source/cutoff/policy and `NEEDS_REVIEW` are unchanged; approval state is independent: `PENDING/APPROVED_LOCAL/REJECTED_LOCAL/EXPIRED/INVALIDATED`.
- Backend derives `SecurityContext(user_id, role, auth_session_id)`; no trust in request-supplied user/role, LLM, MCP, RAG or checkpoint. No unowned legacy conversation leakage or auth bypass flag. **Proposed local defaults (review before code):** auth session TTL 8 hours; 5 failed logins per username/IP window of 15 minutes → 15-minute lockout; proposal review expiry 24 hours after submission. Use UTC timestamps; duration choices are not historical cutoff/freshness rules.
- Keep current `workflow_demo.review_run(role='manager')` explicitly **simulated**. No T06 claim of LangGraph `interrupt/resume`. Existing T01–T05 accepted behavior must regress cleanly.
- Never attach generated reports, credential material, traces or screenshot artifacts to repository commits. Distinguish local/mocked, real pinned Fiction, and paid provider evidence.

## Interface and file map

| Owner | Proposed source | Responsibility |
|---|---|---|
| Auth persistence | Create `retailiq/infrastructure/auth.py`; modify `retailiq/infrastructure/sessions.py` | SQLite auth schema, password hashing, sessions, revocation, throttle, conversation owner migration |
| Auth boundary | Create `retailiq/security.py`, `retailiq/api/auth.py`; modify `retailiq/api/http.py` | Typed principal, auth endpoints, default-deny API and CSRF, SSE identity |
| CLI | Create `scripts/manage_users.py`; modify `requirements-offline.txt` | Non-echo local operator provisioning and Argon2id |
| Owned data endpoints | Modify `retailiq/api/sessions.py`, `retailiq/api/logs.py`, `retailiq/orchestration/week1_graph.py` only as needed | Owner checks *before* context/checkpoint use, deny cross-user diagnostics |
| Verified proposal domain | Create `retailiq/domain/uc01_review.py` | Resolve exact pinned Fiction G1 candidate via existing `investigate_backorder` and trusted `_uc01_inputs` contract; no model policy authority |
| Proposal state + API | Create `retailiq/infrastructure/uc01_proposals.py`, `retailiq/api/uc01_proposals.py` | Unique immutable proposal, idempotent creation, Manager-only decision and actor-specific reads |
| Workspace | Modify `frontend/src/main.tsx`, `frontend/src/styles.css`; add `frontend/tests/t06-auth.spec.ts`, `frontend/playwright.config.ts` and a minimal dev-only Playwright runner in `frontend/package.json` | Login/logout, CSRF fetch, eligible Submit, Manager inbox, owned status and account switch; one browser E2E |

## Review focus (each covered by a task test)

1. Legacy `sessions.owner_user_id IS NULL` must not become visible after login or on session ID guessing (Task 2).
2. Logout/revocation between SSE enqueue, dequeue and persistence must not reveal events or commit a new turn (Task 2).
3. `NEEDS_REVIEW` due solely to policy conflict, changed cutoff or missing stock cannot become an approvable candidate (Task 3).
4. Two Analysts/candidates for the same case/source/cutoff and racing Managers must never create contradictory decisions (Tasks 3–4).
5. Origin/CSRF missing or forged, caller-controlled `role=manager`, and `/api/logs` may not bypass security (Tasks 1–2, 4).

---

### Task 1 — Local identity store, credentials, and API authentication

**Files:** Create `retailiq/infrastructure/auth.py`, `retailiq/security.py`, `retailiq/api/auth.py`, `scripts/manage_users.py`, `tests/test_t06_auth.py`; modify `requirements-offline.txt`, `retailiq/api/http.py` (middleware/router integration only).

**Interfaces:** `SecurityContext(user_id: str, role: Literal["analyst","manager"], auth_session_id: str)`; `create_local_user(username: str, role: str, password: str) -> str`; `authenticate_credentials(username: str, password: str) -> str | None`; `issue_auth_session(user_id: str) -> tuple[str,str]` (opaque cookie, CSRF); `principal_from_token(cookie: str) -> SecurityContext | None`; `assert_active(principal: SecurityContext) -> None`; `revoke_session(principal: SecurityContext) -> None`. Cookie and CSRF secrets never enter model, state or logs.

- [ ] **Step 1: Test RED** — Write `test_cli_user_hash_not_plaintext`, `test_invalid_login_returns_generic_401_and_throttles`, `test_cookie_me_logout_revocation_and_disabled_user`, `test_reject_login_cross_origin`, `test_csrf_mismatch_rejected`, `test_unauthenticated_ask_fails_before_ask_mock_called` in `tests/test_t06_auth.py`; assert roles, cookie flags, no plaintext, no `ask()` invocation.
- [ ] **Step 2: Run RED** — `python -m pytest -q tests/test_t06_auth.py`; expect missing modules/routes or failing assertions.
- [ ] **Step 3: Implement GREEN** — Create minimal SQLite users/auth_sessions/login-failure store using existing app DB. Hash passwords with Argon2id; use random 256-bit opaque cookie and stored token hash, server-bound synchronizer CSRF, strict same-origin/Referer check, expiry/revocation, bounded auth attempts, and generic errors. `/api/auth/login`, `/api/auth/me`, `/api/auth/logout` return `Cache-Control: no-store`.
- [ ] **Step 4: Run GREEN** — Same pytest command; inspect HTTP `Set-Cookie` and missing-Origin negative. Verify `python -m scripts.manage_users --help` (no credentials in output).
- [ ] **Step 5: Commit** — Commit implementation and test changes **only to the feature branch**.

### Task 2 — Owner-scoped conversation, APIs and revocation-aware SSE

**Files:** Modify `retailiq/infrastructure/sessions.py`, `retailiq/api/sessions.py`, `retailiq/api/http.py`, `retailiq/api/logs.py`, `retailiq/orchestration/week1_graph.py` only if necessary; create `tests/test_t06_ownership_sse.py`; update existing API test fixtures to authenticate explicitly (no hidden bypass).

**Interfaces:** `create_session(title: str, *, owner_user_id: str) -> dict`; `get_session(sid: str, *, owner_user_id: str, include_messages: bool=True) -> dict|None`; `list_sessions(*, owner_user_id: str, limit: int=50) -> list[dict]`; session history/memory/trace/delete/load-case-binding require the same owner. `_perform_turn(data: AskBody, principal: SecurityContext) -> dict`; `add_turn(..., *, principal: SecurityContext)` validates owner and active auth **in the write transaction**; SSE worker receives server-created principal, not browser-supplied identity.

- [ ] **Step 1: Test RED** — `test_ownerless_legacy_migration_fails_closed`, `test_two_users_session_memory_trace_and_checkpoint_isolation`, `test_unauthenticated_business_and_diagnostics_401`, `test_session_revoked_while_sse_queued_drops_private_events_and_final`, `test_revoked_before_turn_commit_adds_no_messages`, `test_account_switch_disallows_old_stream`.
- [ ] **Step 2: Run RED** — `python -m pytest -q tests/test_t06_ownership_sse.py`; expect failing ownership/revocation assertions.
- [ ] **Step 3: Implement GREEN** — Idempotent nullable `owner_user_id` DB migration; owner-filtered SQL everywhere; default-deny middleware for `/ask`, `/ask/stream`, sessions, ROI, workflows, logs and other business routes. Auth/session checks before LLM work, at transactional turn persistence, at SSE enqueue **and** yield. Deny unscoped log viewer; do not cancel already-running synchronous LLM artificially.
- [ ] **Step 4: Run GREEN** — Same pytest command plus `python -m pytest -q tests/test_fiction_request_boundaries.py` using explicit auth test clients; no unauthenticated success fixtures.
- [ ] **Step 5: Commit** — One reviewed, self-contained authorization slice; no partial unprotected endpoint path exposed in final PR.

### Task 3 — Verified UC-01 proposal creation and owner-scoped reads

**Files:** Create `retailiq/domain/uc01_review.py`, `retailiq/infrastructure/uc01_proposals.py`, `retailiq/api/uc01_proposals.py`, `tests/test_t06_proposals.py`; register router in `retailiq/api/http.py`.

**Interfaces:** `verified_candidate(case_binding: dict, candidate_snapshot_id: str|None) -> dict` returns a canonical immutable candidate from pinned `FictionStore`/policy/cutoff (no LLM); `submit_proposal(owner_user_id: str, canonical: dict) -> dict`; `get_eligibility(session_id: str, principal: SecurityContext) -> dict`. API: `GET /api/uc01/eligibility?session_id=...`, `POST /api/uc01/proposals` (`session_id`, optional `candidate_snapshot_id`), `GET /api/uc01/my-proposals`, Manager-only `GET /api/uc01/proposals` and `/{id}`.

- [ ] **Step 1: Test RED** — `test_g1_pinned_candidate_proposal_has_exact_case_cutoff_policy_and_available_units`; `test_needs_review_policy_conflict_or_missing_candidate_is_not_eligible`; `test_multiple_candidates_require_explicit_verified_snapshot`; `test_repeated_same_owner_candidate_is_idempotent`; `test_same_case_different_owner_or_candidate_conflicts`; `test_manager_inbox_omits_analyst_chat_and_memory`.
- [ ] **Step 2: Run RED** — `python -m pytest -q tests/test_t06_proposals.py` with pinned real Fiction release when present, controlled fixture for absent/adversarial candidates; **label each mode**.
- [ ] **Step 3: Implement GREEN** — Reuse `retailiq/domain/backorder.py::investigate_backorder` and verified source/cutoff checks (do not duplicate business arithmetic); persist bounded snapshot + canonical SHA fingerprint, `UNIQUE(case_id,source_sha256,cutoff)`, review-window expiry; never accept policy/cutoff supplied by caller. Unowned or nonmatching principal returns no proposal details.
- [ ] **Step 4: Run GREEN** — Same tests; verify no Fiction table mutation by before/after source-hash or SQL oracle.
- [ ] **Step 5: Commit** — Proposal/domain slice, no Manager decision authority yet.

### Task 4 — Authenticated Manager decision with single-use SQLite CAS

**Files:** Modify `retailiq/infrastructure/uc01_proposals.py`, `retailiq/api/uc01_proposals.py`; create `tests/test_t06_manager_decision.py`.

**Interfaces:** `decide_proposal(proposal_id: str, decision: Literal["approve","reject"], expected_version: int, reviewer: SecurityContext) -> dict`; API `POST /api/uc01/proposals/{id}/decision`. Decision record: `status`, incremented `version`, `reviewed_by`, `reviewed_at` in **one** SQLite transaction.

- [ ] **Step 1: Test RED** — `test_manager_can_approve_or_reject_exactly_once`, `test_analyst_role_spoof_and_self_review_denied`, `test_stale_version_duplicate_and_two_manager_race_one_winner`, `test_expired_or_source_changed_proposal_denied`, `test_crash_before_commit_no_decision_and_after_commit_single_durable_decision`, `test_fiction_operational_tables_unchanged`.
- [ ] **Step 2: Run RED** — `python -m pytest -q tests/test_t06_manager_decision.py`; expect missing action / failing CAS assertions.
- [ ] **Step 3: Implement GREEN** — Re-verify pinned source, candidate, policy and original cutoff; enforce Manager role, reviewer != owner, active auth and CSRF; atomic `UPDATE ... WHERE status='PENDING' AND version=? AND expires_at>?` (exactly one row); return bounded local decision/status. No transfer/reservation, second store or graph resume.
- [ ] **Step 4: Run GREEN** — Same tests including concurrent SQLite connections; inspect DB decision row and unchanged Fiction oracle.
- [ ] **Step 5: Commit** — Only CAS/status/security changes for this slice.

### Task 5 — Workspace integration and end-to-end evidence

**Files:** Modify `frontend/src/main.tsx`, `frontend/src/styles.css`; create `tests/test_t06_http_e2e.py`, `frontend/tests/t06-auth.spec.ts`, `frontend/playwright.config.ts`; modify `frontend/package.json` for one dev-only Playwright E2E command. No general browser-test framework beyond this scenario.

**Interfaces:** `/api/auth/me` bootstraps in-memory CSRF; no cookie/token in `localStorage`. React loads account-scoped conversation and `/api/uc01/my-proposals`, renders eligibility via server endpoint after reload, submits verified proposal, and shows Manager queue/decision without Analyst messages.

- [ ] **Step 1: Test RED** — `test_api_login_analyst_submit_manager_decide_owner_readback`, `test_relogin_switch_account_cannot_restore_old_session`, `test_wrong_role_origin_csrf_or_stale_evidence_fails_closed` in `tests/test_t06_http_e2e.py`; browser scenario: login Analyst → investigate G1 → submit → logout → Manager review → Analyst reload → status, with no Fiction write.
- [ ] **Step 2: Run RED** — `python -m pytest -q tests/test_t06_http_e2e.py`; the browser scenario `npm --prefix frontend run test:e2e -- t06-auth.spec.ts` also fails against pre-T06 frontend after a minimal test server setup.
- [ ] **Step 3: Implement GREEN** — Minimal login/logout and proposal controls; all protected `fetch` POST/PUT/DELETE requests send CSRF+same-origin; `401` clears account-specific app state and stale `retailiq-workspace-session`. Keep graph display truthful and label any legacy demo role selector as simulated.
- [ ] **Step 4: Run GREEN** — `python -m pytest -q tests/test_t06_auth.py tests/test_t06_ownership_sse.py tests/test_t06_proposals.py tests/test_t06_manager_decision.py tests/test_t06_http_e2e.py`; `npm --prefix frontend run build`; `npm --prefix frontend run test:e2e -- t06-auth.spec.ts` against local API + compiled Workspace; store screenshots/logs as external PR evidence, not committed fixture.
- [ ] **Step 5: Review, broader targeted regressions, commit and PR** — Re-run relevant UC-01 T01–T05 tests and static/negative security audits; review API route map for bypass. PR lists original design SHA, exact test commands, source mode and remaining gaps. Never mark T06 accepted from code existence/green mock CI alone.

## Final acceptance / rollout

- Review all **S09-A01–A10** and T06 parent [#34](https://github.com/hungtvb/retailIQ/issues/34) criteria against actual HTTP/SQLite/SSE/browser evidence; test two accounts and adversarial input, not just unit tests.
- Migration rollout: pre-existing ownerless chats are **inaccessible**; provide explicit local archival/disposal instruction (no implicit ownership). The authenticated app requires CLI-created users before regular use.
- Include `pwdlib[argon2]` only once, pin version compatible with Python 3.12 after checking official dependency docs; do not turn this into OAuth, production-grade IAM or a separate service.
- Update `docs/ARCHITECTURE.md`/`docs/DATA_API.md` only where API/architecture changes require; keep README quick start minimal. Sync owner #29, parent #34 and ledger **after actual acceptance evidence**. T07 UI and T08 full UC-01 E2E stay separately tracked.
- **Plan review gate:** This document must be reviewed and approved before implementation; no product code, acceptance claim or merge authorized by the plan alone.

**Official references:** [FastAPI response cookies](https://fastapi.tiangolo.com/advanced/response-cookies/) · [OWASP CSRF prevention](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html) · [SQLite UPSERT / uniqueness](https://www.sqlite.org/lang_upsert.html).
