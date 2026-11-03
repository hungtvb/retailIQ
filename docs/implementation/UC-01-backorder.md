# UC-01 — Backorder Investigation · Implementation Detail

**Status:** DRAFT FOR REVIEW (not implementation approval) · **Design baseline:** RetailIQ `main@69c4bf4`, Fiction `fiction-retail-unified-v1.0.0` · **Scope:** one read-only end-to-end vertical slice.

**References:** [Basic Design](../DESIGN.md) · [Fiction runtime](../FICTION_RUNTIME.md) · [Data/API semantics](../DATA_API.md) · [Review 02 / context #22](https://github.com/hungtvb/retailIQ/issues/22) · [Review 03 / orchestration #23](https://github.com/hungtvb/retailIQ/issues/23) · [Review 08 / evidence #28](https://github.com/hungtvb/retailIQ/issues/28) · [Fiction source contract](https://github.com/hungtvb/fiction-retail/blob/main/docs/DATA_CONTRACT.md).

## 1. Problem, outcome and boundary

**User question:** “Investigate backorder case CASE-…: could another warehouse cover the requested quantity *at the case evidence cutoff*, which policy applied, and what decision is still needed?” Follow-ups may ask about a particular warehouse or the applicable policy without losing the case identity/cutoff.

**Expected outcome:** a source-addressable investigation with verified partial facts, alternative-warehouse observations, policy applicability and an explicit business disposition. **No shipment/stock/order mutation; no transfer execution.** An observation that passes stock/cutoff checks is **not** a transfer approval. Manager HITL belongs to [#29](https://github.com/hungtvb/retailIQ/issues/29) and must not be faked with a caller-supplied role.

**Milestone boundary:** M0 already merged in [PR #33](https://github.com/hungtvb/retailIQ/pull/33); this design covers the **next implementation**. The current `/ask`, LangGraph, MCP, RAG and workspace still use legacy/demo paths for much of their execution. The diagram below is **target behavior, not implemented Fiction UC-01 evidence**.

## 2. Target execution flow

~~~mermaid
flowchart TD
    U[Operator asks about CASE ID] --> API[Existing /ask or /ask/stream]
    API --> CX[Resolve session / explicit case reference]
    CX --> PLAN[Bounded capability plan: UC-01 template]
    PLAN --> CASE[FictionStore: fulfillment_case + order facts]
    CASE --> FIT[Trusted evidence fitness: ID, cutoff, snapshots, route]
    PLAN --> POLICY[Policy registry + source document by case cutoff]
    POLICY --> FIT
    FIT --> VERDICT{Enough trusted evidence?}
    VERDICT -->|Yes| REVIEW[Findings + transfer proposal needs manager review]
    VERDICT -->|Partial / conflicting| PARTIAL[Verified facts + gaps; no unsupported transfer verdict]
    REVIEW --> ANSWER[Authoritative AnswerResult + evidence refs]
    PARTIAL --> ANSWER
    ANSWER --> UI[Chat + actual execution events]
~~~

**Control rule:** `resolve → plan once → validate → execute bounded reads → verify → assemble → finish`. The LLM may interpret user phrasing or **propose** registered capabilities, but may not select unrestricted SQL, invent policy validity, alter case IDs, decide authorization or certify its own evidence. Use the fixed UC-01 DAG before considering adaptive supervisor.

**Request lifecycle:** one execution per request; only successfully verified answer/evidence is committed to session history. `/ask/stream` emits observable execution events and a single authoritative final `result`; do **not** stream unverified factual draft tokens. The graph renders observed invocation/return events, not hypothetical agent nodes ([#21](https://github.com/hungtvb/retailIQ/issues/21), [#30](https://github.com/hungtvb/retailIQ/issues/30)).

## 3. Source-to-code mapping — reuse first

| Responsibility | Existing source / owner | Necessary addition (not yet implemented) |
|---|---|---|
| Chat request/session | `retailiq/api/http.py`, `retailiq/infrastructure/sessions.py` | Route UC-01 request through current endpoints; persist only committed, case-linked evidence (#22) |
| Capability planning/execution | `retailiq/orchestration/week1_graph.py` | Registered, validated fixed UC-01 task plan, bounded calls and trace (#23); no new graph engine |
| Case, order, snapshot, eligibility SQL | `retailiq/domain/fiction.py` `FictionStore.open()` / `fulfillment_case()` / `order()` | **Reuse as-is first**; add only targeted read-only domain operation if a tested missing fact requires it |
| Release/access boundary | `retailiq/infrastructure/sqlite.py`, `data/fiction/manifest.json` | Explicit local Fiction DB; release hash/integrity/WAL gate; no `EL-###`/VND fallback |
| Effective policy evidence | Fiction `fulfillment_policies`, `knowledge_documents` registry + source Markdown; existing `retailiq/rag/` | Resolve **exact warehouse policy ID + validity at case cutoff** (#27); do not infer effective dates from `fulfillment_policies` table alone |
| Business verification | Existing case exclusions + Review 08 [#28](https://github.com/hungtvb/retailIQ/issues/28) | Shared source/identity/time/policy gate and qualified final disposition; no second verifier agent |
| UI / tracing | `retailiq/observability.py`, `frontend/src/main.tsx`, `frontend/src/graph.ts` | Display actual evidence/limitations and observed execution, not synthetic approvals (#30) |

The Fiction release stores **100 selected investigations**, not a full inventory ledger. `inventory_snapshots_v2` / `operational_events` are case-scoped; base `inventory` has **no stock observation timestamp** and cannot replace case evidence. The release has **zero actual received-after-cutoff snapshots**; that negative path requires a controlled adversarial fixture, not a claimed real-release example.

## 4. Input/output and deterministic acceptance contract

**Input (proposed, versioned at integration):** `request_id`, `session_id`, user question, explicit/inherited `case_id`, optional `warehouse_id` and requested action `investigate`. Validate `CASE-<UUID>`, canonical `order_id`/`order_item_id`/`product_id`, requested quantity and scoped warehouse. Resolve inherited references only from **committed same-session evidence**, not an LLM assertion or a refreshed ranking (#22). Principal/role, when #29 lands, come from the authenticated backend, **never** request/LLM payload.

**Trusted business reads:** `fulfillment_case(case_id)` yields `case`, `cutoff`, `snapshots`, `warehouse_eligibility`, `evidence_candidates`, `candidate_gap_reasons` plus `source` (release/hash), `scope`, `record_refs`, `temporal` and `limitations`. `order(order_id)` must match the case's order item/product; mismatch blocks the joined claim. **No generic LLM-generated SQL**.

**Case-evidence gate (deterministic):**
1. Exactly one `evidence_cutoff_reached` event; validate timestamps and quantity; keep original cutoff unchanged across follow-ups.
2. Filter by same `case_id` and `product_id`; both `observed_at` **and** `received_at` must be ≤ cutoff; observation age ≤ 24 hours. Reject invalid chronology.
3. Use the **latest available-at-cutoff observation per warehouse**; a newer insufficient snapshot supersedes an older favorable one. Reject assigned warehouse, denied/unknown route and insufficient available quantity (`on_hand - reserved < request_qty`).
4. Surface rejected snapshots with explicit reason codes and evidence references. `NO_CASE_SNAPSHOT` ≠ zero stock; historical/case observations ≠ current/live inventory.
5. Validate policy ID, source document checksum/version and effective interval **at the case cutoff**, not at the dataset `as_of`. Fiction's warehouse policy `FR-WH-2026-10-04` applies for **[2026-10-04, 2026-11-03)**; verify via registry/document metadata (the SQL `fulfillment_policies` table carries summary/approval flag, **not** effective-date columns). Missing/overlapping/expired policy must not silently become “current.”

**Proposed final answer envelope:** keep existing `AnswerResult` fields (`answer`, `records`, `contexts`, `request_id`); add only the integration fields agreed in #28/#30: `disposition` (`SUPPORTED | NEEDS_REVIEW | INSUFFICIENT_EVIDENCE`), bounded `findings` with supporting `evidence_refs`, `limitations`, and actual trace/`source` metadata. Do not create a second answer schema.

**Status rules:** `SUPPORTED` can qualify *factual* case/snapshot findings. A proposed warehouse transfer **requires manager review** even when qualifying evidence is complete (`NEEDS_REVIEW` for the proposed decision). Missing/stale/conflicting evidence must yield `INSUFFICIENT_EVIDENCE` for that decision, while still showing supported partial facts. Tool execution failure is an execution error, **not** automatically an evidence-insufficiency verdict.

## 5. Acceptance scenarios — implement tests before business wiring

| ID | Scenario / independent expected outcome | Evidence mode |
|---|---|---|
| UC01-A | Case exists, alternative snapshot valid at cutoff, route eligible, stock sufficient, dated policy applicable → candidate evidence, **not** automatic transfer | Independent SQL oracle + dated policy registry |
| UC01-B | Case missing / mismatched order, line, product or warehouse → fail closed, original scope preserved | Fixture + SQL/contract check |
| UC01-C | No snapshot / only stale or insufficient / assigned warehouse → verified facts + reasons, no “zero stock” or positive candidate claim | Actual cases + independent SQL oracle |
| UC01-D | Received after cutoff / observed after cutoff / superseded latest snapshot → exclusion reason, no late-evidence use | **Fixture** (not present in published real cases) |
| UC01-E | Policy expired, missing, conflicting, wrong product/release or injected source text → no policy-based decision | Dated-registry/RAG adversarial fixture |
| UC01-F | “What about warehouse two?” and “which policy applied?” → preserve exact case/cutoff/warehouse from **committed** answer; wrong-session or ambiguous reference clarifies | Context + actual tool args |
| UC01-G | Model suggests unauthorized capability / plan omits required evidence; tool timeout; SSE disconnect → bounded fail-closed execution, no fabricated results or actions | Mocked plan/HTTP scenarios |
| UC01-H | One real LLM run for this **wired UC-01 path**: observe actual tool invocation IDs, expected case/warehouse/cutoff, grounded response and usage/trace | Provider-backed CI + independent oracle; **PENDING** |

**Run gates:** existing `python -m scripts.verify_fiction_runtime --db data/fiction/fiction_retail.sqlite --manifest data/fiction/manifest.json` is **M0 only**; it does **not** test UC-01 orchestration, policy retrieval, context or UI. Add a small scenario test through the actual newly wired path, then current-commit CI and provider-backed CI only when its new model path can be exercised. Log commit, release SHA, exact input, expected/observed IDs/cutoff, test mode, trace refs and known gaps. Never mark a course CAP PASS from a mock or an illustration.

## 6. Implementation order and stop conditions

1. **M1 read-only vertical slice:** reuse `FictionStore`, add missing policy/verification checks only as needed; independent positive/negative business oracle (#28). Keep it callable deterministically without Agent.
2. **M2 integration:** register minimal capabilities, wire fixed bounded LangGraph plan (#23), committed-evidence context (#22), exact policy-document retrieval (#27) and **optional real MCP path only where #26 requires it**. Do not make all SQL calls go through MCP.
3. **M3–M5 acceptance:** real auth/HITL (#29) before any approval claim, verified-first SSE and truthful graph (#21/#30), then Fiction UC-01 real LLM + source/versioned E2E evidence.

**Implementation gate:** review/merge this design into `main` **before** a feature code PR; that code PR must link this path + approved design commit and state deviations. Significant changes to capability, temporal, policy or trust contracts require design review first. Small clarifications may travel in the code PR only when the approved behavior is unchanged. No separate UC-01 microservice, agent framework, event bus, extra source database or unrequested action endpoints.
