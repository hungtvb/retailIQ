# UC-01 — Backorder Investigation · Implementation Detail

**Approval gate:** only a reviewed design revision merged to `main` is an implementation contract (a docs PR is a proposal) · **Design baseline:** RetailIQ `main@69c4bf4`, Fiction `fiction-retail-unified-v1.0.0` · **Scope:** one read-only end-to-end vertical slice.

**References:** [Basic Design](../DESIGN.md) · [Fiction runtime](../FICTION_RUNTIME.md) · [Data/API semantics](../DATA_API.md) · [Review 02 / context #22](https://github.com/hungtvb/retailIQ/issues/22) · [Review 03 / orchestration #23](https://github.com/hungtvb/retailIQ/issues/23) · [Review 08 / evidence #28](https://github.com/hungtvb/retailIQ/issues/28) · [Fiction source contract](https://github.com/hungtvb/fiction-retail/blob/main/docs/DATA_CONTRACT.md).

## 1. Problem, outcome and boundary

**User question:** “Investigate backorder case CASE-…: could another warehouse cover the requested quantity *at the case evidence cutoff*, which policy applied, and what decision is still needed?” Follow-ups may ask about a particular warehouse or the applicable policy without losing the case identity/cutoff.

**Expected outcome:** a source-addressable investigation with verified partial facts, alternative-warehouse observations, policy applicability and an explicit business disposition. **No shipment/stock/order mutation; no transfer execution.** An observation that passes stock/cutoff checks is **not** a transfer approval. Manager HITL belongs to [#29](https://github.com/hungtvb/retailIQ/issues/29) and must not be faked with a caller-supplied role.

**Milestone boundary:** M0 [#33](https://github.com/hungtvb/retailIQ/pull/33) and deterministic UC-01 T01 [#37](https://github.com/hungtvb/retailIQ/pull/37) have merged. T02 [#40](https://github.com/hungtvb/retailIQ/pull/40) wires an **explicit CASE-ID-only** LangGraph/`/ask` template, verified with **mock-provider + real SQLite fixture**. T03 [#44](https://github.com/hungtvb/retailIQ/pull/44) adds **committed-session case binding** for policy/alternative-warehouse follow-ups, with explicit source/cutoff re-verification; ambiguous positional warehouses require clarification. This is **not** the complete conversation-context capability in #22. The diagram remains a **full target flow**, not evidence that Fiction MCP/RAG/HITL/UI or real-provider UC-01 E2E are accepted.

## 2. Target execution flow

~~~mermaid
flowchart TD
    U[Operator: investigate CASE ID] --> API[Existing /ask or /ask/stream]
    API --> CX[Resolve explicit or committed-session case reference]
    CX --> PLAN[Validate bounded UC-01 capability plan]
    PLAN --> CASE[FictionStore: fulfillment_case + order]
    CASE --> IDENT{Identity and exactly one cutoff valid?}
    IDENT -->|No| STOP[Clarify / deny / fail closed]
    IDENT -->|Yes: bind case ID and cutoff| POLICY[Exact warehouse policy registry and source Markdown]
    IDENT -->|Verified case facts| FACT[Assess case-scoped snapshots, freshness, route and qty]
    POLICY --> JOINT[Verify policy, source versions and business claim]
    FACT --> JOINT
    JOINT --> OUT{Evidence-backed disposition}
    OUT -->|Eligible candidate + policy| REVIEW[Proposal requires manager review; no mutation]
    OUT -->|Verified exclusions only| NEG[Scoped negative finding, no transfer]
    OUT -->|Missing / conflicting evidence| PARTIAL[Verified partial facts + explicit gaps]
    REVIEW --> ANSWER[Authoritative AnswerResult + evidence refs]
    NEG --> ANSWER
    PARTIAL --> ANSWER
    ANSWER --> UI[Chat + actual observed execution events]
~~~

**Dependency invariant (B1):** the policy task **cannot run** from the initial plan alone. It requires a validated `case_id`, order-item/product scope, and exactly one `evidence_cutoff_reached` obtained from `FictionStore.fulfillment_case(case_id)`. Persist that cutoff as a typed output binding in the fixed UC-01 DAG. A model-supplied/current-date cutoff, policy ID or unverified prior chat text must not bypass the gate. Case facts and policy may join for verification **only after** both are bound to the same source release and cutoff.

**Control rule:** `resolve → plan once → validate → execute bounded reads → verify → assemble → finish`. The LLM may interpret phrasing/propose registered capabilities, but may not write unrestricted SQL, choose policy validity, alter case IDs, decide authorization or certify evidence. Use a fixed dependency DAG; no adaptive supervisor for UC-01 without a tested need.

**Request lifecycle:** one execution per request, committed same-session evidence only (#22); only verified results/evidence are stored. `/ask/stream` emits actual execution events plus **one authoritative final `result`**. Do not stream unverified factual draft text; graph edges reflect observed calls/returns, not hypothetical agents (#21/#30). Reject mismatched scope before policy/RAG work or business conclusions.

## 3. Source-to-code mapping — reuse first

| Responsibility | Existing source / owner | Necessary addition (not yet implemented) |
|---|---|---|
| Chat request/session | `retailiq/api/http.py`, `retailiq/infrastructure/sessions.py` | Route UC-01 request through current endpoints; persist only committed, case-linked evidence (#22) |
| Capability planning/execution | `retailiq/orchestration/week1_graph.py` | Registered, validated fixed UC-01 task plan, bounded calls and trace (#23); no new graph engine |
| Case, order, snapshot, eligibility SQL | `retailiq/domain/fiction.py` `FictionStore.open()` / `fulfillment_case()` / `order()` | **Reuse as-is first**; add only targeted read-only domain operation if a tested missing fact requires it |
| Release/access boundary | `retailiq/infrastructure/sqlite.py`, `data/fiction/manifest.json` | Explicit local Fiction DB; release hash/integrity/WAL gate; no `EL-###`/VND fallback |
| Effective policy evidence | Fiction `fulfillment_policies`, `knowledge_documents` and `knowledge/policies/FR-WH-2026-10-04.md` | **Deterministic exact policy lookup by verified case cutoff** + registry/document hash, source-version and effective-interval checks; policy RAG only explains verified text (#27), never selects binding applicability |
| Business verification | Existing case exclusions + Review 08 [#28](https://github.com/hungtvb/retailIQ/issues/28) | Shared source/identity/time/policy gate and qualified final disposition; no second verifier agent |
| UI / tracing | `retailiq/observability.py`, `frontend/src/main.tsx`, `frontend/src/graph.ts` | Display actual evidence/limitations and observed execution, not synthetic approvals (#30) |

The Fiction release stores **100 selected investigations**, not a full inventory ledger. `inventory_snapshots_v2` / `operational_events` are case-scoped; base `inventory` has **no stock observation timestamp** and cannot replace case evidence. The release has **zero actual received-after-cutoff snapshots**; that negative path requires a controlled adversarial fixture, not a claimed real-release example.

## 4. Input/output and deterministic acceptance contract

**Input (proposed, versioned at integration):** `request_id`, `session_id`, user question, explicit/inherited `case_id`, optional `warehouse_id` and requested action `investigate`. Validate `CASE-<UUID>`, canonical `order_id`/`order_item_id`/`product_id`, requested quantity and scoped warehouse. Resolve inherited references only from **committed same-session evidence**, not an LLM assertion or a refreshed ranking (#22). Principal/role, when #29 lands, come from the authenticated backend, **never** request/LLM payload.

**Trusted business reads:** `fulfillment_case(case_id)` yields `case`, `cutoff`, `snapshots`, `warehouse_eligibility`, `evidence_candidates`, `candidate_gap_reasons` plus `source` (release/hash), `scope`, `record_refs`, `temporal` and `limitations`. `order(order_id)` must match the case's order item/product; mismatch blocks the joined claim. **No generic LLM-generated SQL**.

**Case-evidence gate (deterministic):**
1. Verify the case/order/line/product/quantity relation using `fulfillment_case(case_id)` and `order(order_id)`; the selected `order_item_id` must belong to that order and product. Exactly one valid `evidence_cutoff_reached` exists; preserve its ISO timestamp (with offset) across follow-ups.
2. Only case-scoped snapshots for the same `product_id` are eligible; both `observed_at` **and** `received_at` must be ≤ cutoff, `received_at >= observed_at`, observation age ≤24 h. Inventory base table has no observation timestamp and **cannot** replace missing case evidence.
3. Select the latest available-at-cutoff observation **per warehouse**; a newer insufficient snapshot supersedes an older favorable one. Exclude assigned warehouse, unknown/denied route and `on_hand - reserved < request_qty`. Preserve `snapshot_id`, `warehouse_id`, timestamps and rejection reasons.
4. Distinguish **recorded alternatives with verified exclusions**, **no case snapshot**, and **unknown/incomplete alternative coverage**. `NO_VERIFIED_ALTERNATIVE_WAREHOUSE_CANDIDATE` describes only the **recorded, evaluated scope**; it never proves there is no stock anywhere. `NO_CASE_SNAPSHOT` is not zero on-hand stock.

**Exact policy lookup and provenance (B2):**

1. **Input dependency:** accept only the validated `case_id` and `cutoff` from step 1. Use the pinned Fiction release `fiction-retail-unified-v1.0.0` and select its **warehouse transfer** policy, not returns/pricing policy and not a semantic-search guess.
2. **Registry binding:** locate exactly one `fulfillment_policies.policy_id = FR-WH-2026-10-04`; join `knowledge_documents` on exact `policy_id` with `kind='business_policy'`. Require a unique `document_id`, `relative_path`, SHA-256 and the expected `requires_manager_approval` flag. The registry **does not contain validity dates**; do not pretend it does.
3. **Document integrity:** read the *local release's* `knowledge/<relative_path>` (expected `knowledge/policies/FR-WH-2026-10-04.md`), reject traversal/missing files, hash original Markdown bytes against `knowledge_documents.sha256`, and ensure the documents/registry/manifest belong to the **same pinned release**. No GitHub network dependency at runtime; reject unverified or mismatched source versions.
4. **Validity authority:** use the **release-locked, reviewed policy interval mapping** from Fiction's [Data Contract](https://github.com/hungtvb/fiction-retail/blob/main/docs/DATA_CONTRACT.md): `FR-WH-2026-10-04 → [2026-10-04, 2026-11-03)` in `Asia/Ho_Chi_Minh` (the policy Markdown displays 4 Oct–2 Nov inclusive). Implement as the smallest trusted config/typed mapping (or reuse an existing one), **not** filename-derived or LLM-extracted dates. Cross-check ID and effective statement against the verified document; an ambiguity/mismatch fails closed. Compare **timezone-normalized case cutoff** against that half-open interval, **not** `dataset_business_as_of=2026-11-03`.
5. **Decision rule:** missing/expired policy, hash mismatch, incompatible release, two overlapping authoritative policies without precedence, or inconsistent approval requirements block **transfer recommendation**. A verified policy conflict yields `NEEDS_REVIEW` for **evidence adjudication**, not an approval-ready transfer proposal. Surface exact reason codes and bounded policy evidence refs (e.g. `fulfillment_policies/FR-WH-2026-10-04`, `knowledge_documents/<document_id>`); RAG can supply a cited explanation **only after** applicability has been established deterministically.

**Policy implementation note:** do not add validity columns to Fiction SQLite, fetch the upstream repo at runtime, create a new policy database, or use embedding similarity to establish policy authority. If local source documents/registry are not yet imported (#27), the policy gate stays **unverified**; no policy-backed decision is marked PASS.

**Proposed final answer envelope:** keep existing `AnswerResult` fields (`answer`, `records`, `contexts`, `request_id`); add only the integration fields agreed in #28/#30: `disposition` (`SUPPORTED | NEEDS_REVIEW | INSUFFICIENT_EVIDENCE`), bounded `findings` with supporting `evidence_refs`, `limitations`, and actual trace/`source` metadata. Do not create a second answer schema.

**Status semantics (B3):** keep three orthogonal concepts: **execution** (completed / failed / denied), **evidence fitness for each finding** (`USABLE | QUALIFIED | BLOCKED`, #28), and **business conclusion disposition** (`SUPPORTED | NEEDS_REVIEW | INSUFFICIENT_EVIDENCE`, #30). Manager approval state is separate and is never inferred from `disposition`.

| Verified situation and scope | Finding / requested decision | Business disposition | Next action |
|---|---|---|---|
| At least one case-scoped alternative candidate passes snapshot/route/quantity and applicable policy is verified | Candidate and eligibility evidence supported; **proposed transfer is not approved** | `NEEDS_REVIEW` for proposed transfer | Authorized Manager review only (#29); no operational mutation |
| All **recorded** alternatives evaluated, with identifiable exclusion reasons and enough evidence for the **narrow question** “any verified candidate in this case?” | **Supported negative finding**: no eligible candidate among evaluated case observations. Never claim all company warehouses lack stock | `SUPPORTED` for scoped *negative finding*; **not** an executable transfer verdict | Report rejected warehouse/reasons and coverage limit; investigate unobserved options separately |
| No case snapshot, stale/late/unknown alternative evidence, policy missing/expired/mismatch, or insufficient coverage for **transfer feasibility** | Supported order/case facts may be shown; actionable transfer feasibility **not established** | `INSUFFICIENT_EVIDENCE` for proposed transfer | Request evidence/policy verification; do not treat missing as zero stock |
| Two authoritative policy documents overlap/conflict without trustworthy precedence | Conflict itself is supported; which policy authorizes a proposal is **unresolved** | `NEEDS_REVIEW` for **policy reconciliation**, explicitly **not** a manager-transfer approval request | Resolve authority; no proposal or mutation |
| SQL/tool/LLM timeout or exception, invalid case identity or forbidden plan | No trustworthy final business result | Execution `FAILED` / `DENIED` (or clarification); **no fabricated business disposition** | Safe error/clarification; do not persist unverified facts |

**Disambiguation rule:** A narrow **negative finding** may be `SUPPORTED` when the recorded alternatives are fully evaluated. That does **not** imply enough evidence to conclude real-world feasibility. If the user's question is broadly “Can any warehouse fulfill?” and coverage is incomplete, the **decision** remains `INSUFFICIENT_EVIDENCE`, even when “no candidate found in evaluated records” is a supported partial fact. Keep the claim's scope and `record_refs` visible.

## 5. Acceptance scenarios — exact golden oracle + adversarial fixtures (B4)

**Published-release SQL golden cases** (independently checked against the local, pinned Fiction SQLite; these **do not** prove Agent/RAG E2E). Each test must assert input `case_id`, exact `cutoff`, canonical order/item/product scope, selected/rejected `snapshot_id`, actual `warehouse_id` and quantity, source/version refs, reason codes and **business disposition** after policy integration.

| Test / user request | Independent expected result at case cutoff | Expected answer contract |
|---|---|---|
| **UC01-G1: eligible alternative**, `CASE-06181249-280d-59b3-b00b-b3de7877eb59` | Cutoff `2026-10-21T11:00:00Z`; requested **1**; alternative warehouse `bd0b4a2e-3f75-46a1-bf8a-5a82594d70a4`; **latest** `SNAP-850016da-7ba6-594a-8532-ca23e4085e89` (`on_hand=6, reserved=1, available=5`), observed `2026-10-21T10:00:00Z`, received `2026-10-21T10:05:00Z`. Warehouse policy effective at cutoff | Candidate evidence **SUPPORTED**; disposition `NEEDS_REVIEW` **for proposed transfer**, no approval or stock write; refs include case, cutoff event, candidate snapshot, warehouse route and exact policy document |
| **UC01-G2: recorded alternative insufficient**, `CASE-15332a00-70bb-59b0-9aa4-a44a7b1a37a9` | Cutoff `2026-10-24T11:00:00Z`; requested **1**; alternative `2f1e95b4-aa81-4b55-926d-70531f59528d`; `SNAP-5ff78bcc-d9e5-5b28-9580-ca4626e316de` has **available=0** and `INSUFFICIENT_AVAILABLE`. No verified candidate from evaluated recorded alternatives | `SUPPORTED` **scoped negative finding** only; no “stock unavailable everywhere” and no transfer proposal. If asked about **all warehouses**, report limited coverage rather than global impossibility |
| **UC01-G3: no case observations**, `CASE-103510dd-95fb-5a4d-9f26-f508b3a73df3` | Cutoff `2026-10-22T11:00:00Z`; requested **1**; **0 case snapshots**; alternative route `90d6c40d-10d6-432b-99fe-bd1448f1aa57` has `ELIGIBILITY_ASSUMED_STOCK_UNKNOWN`. Snapshot limitation `NO_CASE_SNAPSHOT` | Show only supported order/case/route facts; `INSUFFICIENT_EVIDENCE` **for fulfillment/transfer conclusion**, never assert zero stock or negative warehouse inventory |

**Policy oracle (same release):** `FR-WH-2026-10-04`, `knowledge_documents.document_id = DOC-de8b393e-45d7-53f3-b1d4-9366a5d0c134`, path `knowledge/policies/FR-WH-2026-10-04.md`, expected SHA-256 `f3ff7463e67e034360fd87b35c1c71286445be0de1431009591821489bd4d9c8`, effective **[2026-10-04, 2026-11-03)** in Asia/Ho_Chi_Minh, manager approval required. SQL registry binding and source-doc byte hash must be separately verified **at runtime**; listed expected metadata is **not** proof docs were imported into RetailIQ yet.

**Fixture-only negatives** (not claims about the actual 100-case release): `UC01-F1` late-received/observed-after-cutoff, `UC01-F2` newer insufficient snapshot supersedes older sufficient, `UC01-F3` expired/no/overlapping/conflicting policy and wrong/missing doc SHA, `UC01-F4` case/order/item mismatch, `UC01-F5` cross-session wrong case/cutoff or malformed model plan, `UC01-F6` timeout/SSE disconnect. Assert exact exclusions (`RECEIVED_AFTER_CUTOFF`, `OBSERVED_AFTER_CUTOFF`, `SUPERSEDED_BY_NEWER_OBSERVATION`, etc.), stop reasons, source refs and **no unauthorized mutation**. The published release has **zero received-after-cutoff observations and no case whose cutoff is outside the warehouse policy window**; these branches require fixtures.

**Provider/Agent E2E gate — PENDING:** after a real Fiction UC-01 path is wired, use one or more golden case IDs in **actual live LLM CI** and inspect LangGraph execution/trace: requested `case_id`, *actual tool invocation IDs, inputs/outputs*, cutoff, policy lookup, verified candidate IDs, final disposition/findings/limitations, session scope and usage. Compare against the independent SQL/policy oracle; a fluent answer without matching tool arguments and evidence is a FAIL. Record commit, release hash, model/provider, mode, inputs, expected/observed outputs and trace IDs. **M0-only** `python -m scripts.verify_fiction_runtime --db data/fiction/fiction_retail.sqlite --manifest data/fiction/manifest.json` proves none of this.

## 6. Implementation order and stop conditions

1. **M1 deterministic contract gate:** reuse `FictionStore`; validate case/line/cutoff, exact release-locked policy registry/document applicability, business disposition and G1–G3 + critical fixture negatives with independent SQL oracle. This is callable directly **without** claiming Agent/LLM/UI works.
2. **First wired Agent gate (M2):** fixed registered capability DAG (#23) consumes M1, minimal same-session reference handling (#22), one actual `/ask` or `/ask/stream` path and real-provider golden run when configured. Real LLM usage must be identified explicitly, not inferred from mocks. Policy decision uses **exact deterministic lookup** even if #27's explanatory RAG is still pending.
3. **Full UC-01 integration / acceptance (M2–M5):** source-policy RAG explanations (#27), actual MCP invocation only where #26 requires it, truthful evidence/UI/SSE (#21/#30), and authenticated manager review (#29) before **any** claim of authorized HITL. App-facing session/ownership validation must follow #29; a local unauthenticated prototype is not security acceptance. No stock/order/transfer mutation.

**Prioritization remains independent:** drafting UC-01 does not decide whether Backorder or Refund Reconciliation is implemented first. Reuse shared capability issues and create new task issues only for independently verifiable gaps; do not block all M1 correctness work on complete RAG/MCP/HITL.

**Implementation gate:** review/merge this design into `main` **before** a feature code PR; that code PR must link this path + approved design commit and state deviations. Significant changes to capability, temporal, policy or trust contracts require design review first. Small clarifications may travel in the code PR only when the approved behavior is unchanged. No separate UC-01 microservice, agent framework, event bus, extra source database or unrequested action endpoints.

## 7. T04 — Inventory/Order MCP integration plan

**Owner:** [#26](https://github.com/hungtvb/retailIQ/issues/26); **UC parent:** [#34](https://github.com/hungtvb/retailIQ/issues/34). This is a design amendment, **not** implemented/verified evidence. Preserve the approved T01 case cutoff and T03 same-session evidence contract.

### Execution and scope

- Reuse the existing FastMCP **stdio** server, LangChain MCP adapter, instrumentation and manifest-verified FictionStore. No new server, framework, second dataset or duplicate SQL implementation.
- Expose only read-only inventory_lookup(product_id | sku, warehouse_id?, as_of?) and order_lookup(order_id). Resolve SKU to canonical UUID with FictionStore; reuse FictionStore.inventory() and FictionStore.order(), returning their authoritative source/scope/refs/temporal/limitations envelope.
- Base inventory is **undated**: no trustworthy stock observation timestamp. Without as_of, report quantities with unknown freshness, never live/current. If as_of asks for historical stock, explicitly return unsupported/insufficient evidence **without a historical quantity**. last_restocked_date does not represent observation. Case-scoped snapshots remain exclusive to verified fulfillment_case() / investigate_backorder() and never leak to unrelated product requests.
- Order result contains validated order, lines and shipments, bounded and without customer PII. Distinguish missing product/order, absent inventory evidence, malformed request and transport/source failures; missing stock is not numeric zero.
- Keep the existing deterministic UC-01 investigation and policy checks. Do not invoke MCP redundantly on every case merely to demonstrate technology. For an explicitly requested case-linked order detail, first re-verify case, order ID, cutoff and release; then MCP order_lookup may supply the requested order data if its identity and source hash match. Ordinary bounded Inventory/Order questions may take the MCP route directly.
- Fiction MCP mode must require the pinned Fiction DB and manifest and fail closed; never silently fall back to old EL-SKU / ORD-demo data. Existing legacy direct SQL paths are unaffected. Legacy MCP opt-in requires explicit migration/retirement; do not silently mix two incompatible business schemas.

~~~mermaid
flowchart LR
    U[Validated inventory or order request] --> G[Bounded LangGraph route]
    G --> A[LangChain MCP adapter]
    A --> S[Existing stdio FastMCP server]
    S --> F[Verified FictionStore operation]
    F --> S
    S --> V[Validate tool result, source, identity and scope]
    V --> T[Observed MCP events and authoritative response]
~~~

### Contracts, errors and compatibility

- Preserve the Fiction evidence envelope: data, source.id/version/sha256, scope, record_refs, temporal, limitations. The tool accepts only named typed parameters; never LLM-authored SQL/columns, unverified source selection, role/authorization or writes.
- Decode the actual MCP result and reject tool execution errors before trusting content. Validate shape, source release/hash, UUID/SKU/warehouse/order identity and no unexpected extra scope. A timeout, unavailable subprocess, malformed payload or mismatch must fail closed, not manufacture success or unmarked direct-SQL fallback.
- Emit mcp.tool.started/completed/failed for **actual** invocation only, with request/session correlation and sanitized metadata. Apply row and tool timeout bounds; do not log PII.
- Retain the present pinned MCP SDK v1 range (mcp>=1.28,<2) and LangChain MCP adapters (<1) for this slice. SDK v2 renames FastMCP to MCPServer; defer that independent migration. Confirm exact installed versions and error handling at implementation.
- Targeted code surfaces: existing RetailIQ MCP server/adapter and narrowly scoped graph integration; add domain order-line validation only when an observed gap requires it. Tests and smoke use Fiction fixtures. Update canonical DATA_API and FICTION_RUNTIME documentation with the code PR, not ahead of implementation.

### Acceptance / evidence gates

1. **Real transport:** subprocess stdio handshake, discovery, actual LangChain invocation of both tools, record real tool args/result IDs; migrate scripts/smoke_mcp_stdio.py from legacy demo identifiers.
2. **Independent SQL oracle:** compare product/SKU mapping, warehouse stock arithmetic, order/lines/shipments, source checksum and record refs on the same manifest-verified Fiction fixture/release. Shared SQL equivalence is **not independent-source corroboration**.
3. **Fail-closed negatives:** invalid/unknown identifiers, absent inventory, historical as_of, identity/hash mismatch, unexpected content shape, subprocess failure/timeout, illegal quantity/source values, and attempted mutations. No PII.
4. **User flow:** actual compiled LangGraph + API turn calls a scoped MCP tool and emits persisted request/session-correlated events; case-linked order requests preserve verified case/cutoff/release. Verify separately in mock-provider, real local SQLite and live-LLM modes when each is actually configured; no fake live test claims.
5. **Report:** exact code SHA, release/DB SHA, test commands, expected/observed tool calls and business values, execution mode, PASS/FAIL, blockers and remaining limitations. Generated traces/reports stay outside Git. No #26 or UC-01 T04 acceptance from design merge alone.

**Official references:** [MCP Python SDK v1](https://py.sdk.modelcontextprotocol.io/v1/); [MCP v2 migration](https://github.com/modelcontextprotocol/python-sdk/blob/main/docs/migration.md); [LangChain MCP client and error behavior](https://reference.langchain.com/python/langchain-mcp-adapters/client/MultiServerMCPClient).
