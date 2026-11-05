# UC-02 — Refund Reconciliation · Implementation Detail (Proposed)

**Approval gate:** This is a **design proposal**, not an implementation authorization. Review and merge the documentation PR before feature code; reference the approved commit SHA in subsequent code PRs.  
**Source baseline:** RetailIQ Fiction M0 (PR [#33](https://github.com/hungtvb/retailIQ/pull/33)); Fiction `fiction-retail-unified-v1.0.0`.  
**Tracker:** [UC-02 Parent #35](https://github.com/hungtvb/retailIQ/issues/35). **UC-01 #34 is still open and retains implementation priority.**

**Canonical references:** [RetailIQ Fiction runtime](../FICTION_RUNTIME.md) · [Data/API](../DATA_API.md) · [Basic/Detail Design](../DESIGN.md) · [Fiction Data Contract](https://github.com/hungtvb/fiction-retail/blob/main/docs/DATA_CONTRACT.md) · [Fiction Source Audit](https://github.com/hungtvb/fiction-retail/blob/main/docs/SOURCE_DB_AUDIT.md) · [Returns Policy](https://github.com/hungtvb/fiction-retail/blob/main/knowledge/policies/FR-RET-2026-10-04.md).

## 1. Business problem and bounded outcome

**User job:** “Đối soát return này: số tiền refund ghi nhận có khớp với giá trị đơn hàng và các dòng hàng của sản phẩm được trả không? Vì sao cần Financial Operations kiểm tra?”

**Outcome:** a **read-only**, source-linked reconciliation of one recorded `return_id` against its order and product-line evidence. Clearly explain observed amounts, discrepancies and data limitations; refer suspected inconsistencies for **Financial Operations review**. A recorded refund amount is **not** proof of approved, executed or settled payment; a discrepancy is **not** proof of fraud.

**Not in scope:** initiating/approving refunds, modifying orders/returns/payments, charging customers, assigning fraud risk, confirming eligibility from missing return-item details, retrieving customer PII, a new refund agent/service/framework or a synthetic payment table. The workflow does **not** depend on UC-01 implementation being complete, but UC-02 code should not displace UC-01's accepted delivery priority.

## 2. Minimal execution flow

~~~mermaid
flowchart TD
    U[Operator: return ID or verified session follow-up] --> API[Existing /ask or /ask/stream]
    API --> CX[Validate explicit / committed-session return ID]
    CX --> PLAN[Registered read-only capability plan]
    PLAN --> SQL[FictionStore.refund plus order]
    SQL --> V{Identity / amounts / source usable?}
    V -->|No| STOP[Clarify or safe partial / error]
    V -->|Yes| CALC[Decimal USD comparisons / reason flags]
    CALC --> ASK{Policy explanation requested and available?}
    ASK -->|No| FINAL[Verified monetary findings + limitations]
    ASK -->|Yes| POLICY[Exact returns-policy integrity and temporal gate]
    POLICY --> FINAL
    FINAL --> UI[Existing answer / evidence / observed trace]
~~~

**Control invariant:** `resolve return_id → bounded reads → deterministic verification → optional policy explanation → one authoritative final result`. A model can interpret the question and phrase the evidence-backed explanation; it cannot invent transaction amounts, payment status, product quantities or policy authority. All SQL comes from reviewed, parameterized capabilities; no unrestricted LLM-generated SQL.

**Policy is optional context, not an authority for monetary facts:** exact source lookup may explain why Financial Operations reviews unusual amounts, but never changes the recorded SQL numbers or asserts an approval. Failing the policy-integrity gate blocks **policy-backed claims**, not independently verified numerical comparisons. **First vertical slice: defer policy retrieval/RAG until #27 supplies verified local documents and hash checks.** Before that gate, an explicit policy question receives a truthful limitation, not a fabricated rule. A general policy explanation after #27 is distinct from assessing a particular return's eligibility.

## 3. Data semantics, ownership and known limitations

| Concern | Verified source / minimal reuse | Non-negotiable boundary |
|---|---|---|
| Return identity and amount | `returns(return_id, order_id, product_id, return_date, refund_amount, return_reason_code)`; `FictionStore.refund(return_id)` | One **return**, never a customer-wide query by guessed name; `processed_by` and customer PII are not needed |
| Order | `orders(order_id, total_amount, order_status)`; `FictionStore.order(order_id)` | Recorded order value is not payment settlement |
| Product lines | `order_items(order_item_id, order_id, product_id, quantity, unit_price, discount_pct)` | A return has **no `order_item_id` and no returned quantity**. All matching product lines are an **upper/reference comparison**, not the value of the actually returned units |
| Time | `return_date`; order-level `shipments.delivered_date` if needed to discuss timing | Return date does **not** establish request-submitted/received timestamp, specific item's delivery, item condition or return-policy eligibility |
| Return policy | `knowledge_documents` for **exact** `policy_id=FR-RET-2026-10-04`; local original Markdown with verified SHA | Effective **[2026-10-04, 2026-11-03)**, `Asia/Ho_Chi_Minh`. No `returns_policies` table; avoid guessed or fuzzy applicability |
| Data release | `data/fiction/manifest.json` plus local `fiction_retail.sqlite` verified by `FictionStore.open` | Pinned `fiction-retail-unified-v1.0.0`; no legacy `EL-###`/VND/source fallback, no Supabase runtime dependency |

**Canonical UC-02 monetary reconciliation contract (USD):**

- Validate `returns.refund_amount`, `orders.total_amount` and all contributing `order_items` values as **finite, nonnegative** amounts; require integer positive quantities and integer discount percentages 0–100. Read source SQLite `REAL` via `Decimal(str(value))` (not `Decimal(float)`); perform arithmetic using `Decimal` without intermediate rounding.
- `order_amount = orders.total_amount`; `product_lines_net = Σ(quantity * unit_price * (1 - discount_pct / 100))` over **all** order lines with the exact returned `product_id`. These lines are the **recorded product reference value**, not proof of quantity actually returned.
- `refund_amount = returns.refund_amount`; preserve signed `refund_minus_order` and `refund_minus_product_lines` at full calculation precision. **Only for user-visible USD amounts/differences**, quantize to two decimal places with `ROUND_HALF_UP`. Do not round a difference before classifying an exception.
- **Exactly two authoritative UC-02 exception flags (source-audit tolerance, strict greater-than):** `ABOVE_ORDER_RECONCILIATION` iff `refund_amount > order_amount + Decimal("0.01")`; `ABOVE_PRODUCT_LINES_RECONCILIATION` iff `refund_amount > product_lines_net + Decimal("0.01")`. Equality to the threshold is **not** flagged; differences greater than $0.01 are. These two reason flags alone drive monetary `NEEDS_REVIEW`.
- **Existing code distinction:** `FictionStore.refund()` currently returns strict `refund_above_order_value` / `refund_above_returned_product_lines` booleans (no +$0.01). Treat these as **raw diagnostic comparisons only**: they must **not** drive the UC-02 disposition or be presented as the two source-audit flags. The first implementation slice may add a small mapping/typed result, with tests, but must not silently change existing callers' field meanings.
- **Independent oracle gate:** validate equality, exactly +$0.01, and +$0.02 in focused fixtures. Cross-check the raw `Decimal` policy against independent pinned-release SQLite comparisons `refund > reference + 0.01`; investigate any binary `REAL`/rounding boundary discrepancies before claiming release totals **140 / 350** match. Never alter the oracle merely to make a test pass.
- **No-flag semantics:** “Recorded refund does **not exceed** either tested reference by more than $0.01.” It **does not** mean the amounts equal, the refund is fair, policy-eligible, approved, settled or anomaly-free under other business checks.
- Do not join `returns` to `order_items` and then sum `refund_amount` across multiplied rows. If one order/product has multiple separate returns, preserve each `return_id` and avoid double-counting when reporting totals.
- Missing order/product line, invalid money/discount/quantity, mixed identity or conflicting source version yields a scoped limitation or denial; missing evidence is **not zero**.

**Observed baseline:** released `returns` has **11,934** rows. The Fiction source audit and pinned RetailIQ manifest report **140** return amounts above order value (+$0.01) and **350** above returned product's aggregate order-line value (+$0.01). The sets may overlap. These published aggregates provide an **oracle target**, not evidence that UC-02 chat/agent paths have been implemented or run.

## 4. Result and verification contract

Reuse the existing answer/evidence envelope (`answer`, `records`, `contexts`, `request_id`) and Review 08/10's source/evidence fitness semantics; do not introduce a parallel response schema.

| Situation | Verified finding | Business disposition / limitation |
|---|---|---|
| Source-valid return, one or both +$0.01 anomaly flags | Return/order/product-line amounts, exact USD differences, row IDs | **NEEDS_REVIEW** for financial reconciliation; not proof of bad payment, fraud or return rejection |
| Neither defined above-reference flag | Recorded refund does **not exceed either reference by more than $0.01** (may be a smaller partial refund) | **SUPPORTED** scoped comparison only, **not equality or overall validity**; `PAYMENT_STATUS_UNKNOWN`, `RETURN_ELIGIBILITY_UNVERIFIED` |
| Missing matched product line, ambiguous return scope or missing authoritative source | Partial order/return facts only, if verified | **INSUFFICIENT_EVIDENCE** for affected claim; ask for missing evidence rather than calculate from zero |
| Policy outside validity, unavailable/changed hash, unknown delivery/item condition | Numerical facts still allowed if source-valid | No policy eligibility conclusion; expose `POLICY_NOT_APPLICABLE_OR_UNVERIFIED` |
| Tool/model timeout, invalid ID, bad plan, cross-session reference | No trustworthy completed business conclusion | Execution error / clarification; no fabricated refund decision |

**Evidence refs:** `returns/<return_id>`, `orders/<order_id>`, `order_items/<order_item_id>`, optional verified `knowledge_documents/<document_id>` and `FR-RET-2026-10-04`; include release checksum, exact USD reference basis and relevant date. No customer phone/email/name. Distinguish **execution success**, **evidence fitness** and **business disposition**; never infer authorized human approval.

**Session and UI:** only inherit a `return_id` from **committed, same-session verified evidence** (#22). Return-specific follow-ups retain the correct order and product; “đã trả tiền chưa?” must answer that **settlement cannot be verified**. Existing React workspace presents actual findings, source IDs, limitations and observed execution events (#30), not an invented payment workflow.

## 5. Acceptance scenarios (design, not executed)

| Scenario | Independent expected oracle / important negative |
|---|---|
| **UC02-G1: above-order return** | Independent pinned-release SQL selects `return_id` with `refund_amount > order.total_amount + 0.01`. Assert canonical UUID, row refs, signed USD differences, `ABOVE_ORDER_RECONCILIATION`, `NEEDS_REVIEW` and no payment/fraud claim. G1 may also exceed product-line reference; record both flags truthfully |
| **UC02-G2: product-line-only excess (disjoint from G1)** | Select real `return_id` satisfying `refund_amount > product_lines_net + 0.01 AND refund_amount <= order.total_amount + 0.01`, using **pre-aggregated** `order_items` by `order_id, product_id`. Expect **only** `ABOVE_PRODUCT_LINES_RECONCILIATION`, `NEEDS_REVIEW`; no above-order flag. If no qualifying release record, record an oracle coverage gap instead of fabricating a live ID |
| **UC02-G3: neither excess flag (including partial)** | Independent SQL selects `refund_amount <= order.total_amount + 0.01 AND refund_amount <= product_lines_net + 0.01`, plus a **partial refund below both references** when present. Expect no defined excess flags and a *scoped* `SUPPORTED` comparison; never say amounts are equal or payment/eligibility is proven |
| **UC02-G4: aggregate reconciliation** | Real pinned release independently yields **140** and **350** flags by distinct `return_id`, never SUM on multiplied joins; sample oracle IDs recorded at execution, not fabricated in docs |
| **UC02-F1: unavailable/inconsistent source** | No matching order/product line, mismatched product/order, malformed source money or invalid discount → fail closed / `INSUFFICIENT_EVIDENCE` |
| **UC02-F2: financial edge** | Equality, exactly +$0.01 (**no excess flag**), +$0.02 (**flag**), partial refund, repeated returns for same product/order, multiple matching product lines → Decimal comparison without premature rounding or refund duplication; validate `REAL`/Decimal oracle agreement |
| **UC02-F3: policy / temporal** | Return outside effective interval, mismatched doc hash, missing document, uncertain item condition / submission date → no eligibility or current-policy assertion |
| **UC02-F4: agent/session/transport** | Forged return ID in model plan, cross-session reference, tool/LLM timeout or stream disconnect → safe stop, no leaked PII, no unverified saved answer |

### RetailIQ Chat / Graph acceptance (run only **after** UC-02 is wired)

Select **real canonical UUID** `return_id` values for G1, G2 and G3 from the pinned Fiction SQLite oracle (not invented `RET-XXX` identifiers). For each scripted turn, compare **request → actual registered tool invocation ID/args → read-only source IDs/values → verification result → single final answer → observed graph edges**. The same test must assert no Fiction DB write. This is a **future E2E acceptance contract**, not a claim that the existing UI already implements UC-02.

| Turn (actual Chat input) | Session / independent expected behavior |
|---|---|
| **CHAT-01**, “Kiểm tra khoản hoàn tiền của return `<real-uuid>`; bất thường gì và theo số liệu nào?” | New session, use G1/G2/G3 real release record; actual bounded refund/order tool args match the exact `return_id`, amount and order/product scope; flags/disposition and refs match independent SQL |
| **CHAT-02**, “Vì sao khoản này bị đánh dấu bất thường?” | **Same session** as CHAT-01; preserve verified `return_id`/`order_id`/`product_id` from committed result; explain only the applicable flags and signed differences |
| **CHAT-03**, “Theo chính sách hoàn trả, trường hợp này cần xử lý thế nào?” | **Same session**; if #27's exact local document/hash and temporal authority are not ready, state policy evidence unavailable. If ready, cite verified `FR-RET-2026-10-04` and its historical interval, **not** generic/current policy; do not decide individual eligibility because `return_date` is not verified submission/receipt time and item condition is absent |
| **CHAT-04**, “Đã hoàn tiền thành công cho khách chưa?” | **Same session**; explicit `PAYMENT_STATUS_UNKNOWN`, no fake payment status, success confirmation, fraud allegation or action |
| **CHAT-05**, “Kiểm tra return `not-a-uuid`.” | Reject invalid ID or request valid identifier; never substitute a nearby return, fake result or leak source rows |
| **CHAT-06**, new session: “Khoản refund vừa rồi thì sao?” | No explicit ID nor committed context in **new session** → request clarification, never inherit CHAT-01's return |
| **CHAT-07**, repeat CHAT-01 on G3 normal/partial record | No false `NEEDS_REVIEW`; answer “does not exceed the two reference values beyond threshold”, never “refund definitely correct/paid” |

**UI/observability oracle:** The actual trace must show **real executed** capability/tool call(s) and input IDs, success/error, source refs and final disposition; graph edges are derived from observed events, not a static simulated workflow. One verified final answer owns the monetary claims. Provider-backed tests include model/provider, commit/release checksum, trace IDs and expected/actual outputs. If no provider or local DB is available, report **NOT RUN**, not PASS.

The live release's explicit IDs and expected cent amounts are **to be selected and recorded by the independent SQLite oracle** in the implementation PR; this design does not pretend to have queried the 199 MiB local binary.

## 6. Integration order and evidence gates

1. **Deterministic domain slice:** reuse `FictionStore.refund()` and `order()`; add only the reviewed **authoritative** +$0.01 flags, signed USD differences and missing-evidence classification. Verify G1–G4 and F1–F3 using **pinned real SQLite** plus threshold fixtures; treat existing strict comparison booleans as non-authoritative diagnostics. A source/SQL PASS is **not** an agent PASS.
2. **Bounded agent slice:** reuse #23/#22 to wire one `return_id` request and one same-session follow-up to existing `/ask`/`/ask/stream`; compare *actual* tool inputs, data and output with the independent oracle. Avoid a new `RefundAgent` unless the existing specialist path proves inadequate.
3. **Explanation / UI / transport:** **defer policy retrieval/RAG** until #27 verifies the local source registry/hash/effective interval; a missing policy is an explicit limitation, not a monetary blocker. Use shared MCP (#26) only if an actual tool-boundary requirement warrants it, existing evidence and UI (#28/#30), no fictional HITL/payment actions.
4. **E2E acceptance:** provider-backed turn(s), real trace, browser evidence and negative cases; record SHA, Fiction release/db checksum, mode, request + `return_id`, independent expected vs observed USD amounts, tool invocations, trace IDs, and explicit remaining gaps. Only then update owner Issue evidence/status.

**Stop condition:** if the source cannot establish approval, payment settlement, return-item quantity or policy eligibility, report that limitation and terminate **without** building a fake subsystem to fill the gap. **No feature-code change is part of this design PR.**
