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
    CALC --> POLICY[Optional exact returns-policy evidence]
    POLICY --> FINAL[Verified findings + limitations]
    FINAL --> UI[Existing answer / evidence / observed trace]
~~~

**Control invariant:** `resolve return_id → bounded reads → deterministic verification → optional policy explanation → one authoritative final result`. A model can interpret the question and phrase the evidence-backed explanation; it cannot invent transaction amounts, payment status, product quantities or policy authority. All SQL comes from reviewed, parameterized capabilities; no unrestricted LLM-generated SQL.

**Policy is optional context, not an authority for monetary facts:** exact source lookup may explain why Financial Operations reviews unusual amounts, but never changes the recorded SQL numbers or asserts an approval. Failing the policy-integrity gate blocks **policy-backed claims**, not independently verified numerical comparisons.

## 3. Data semantics, ownership and known limitations

| Concern | Verified source / minimal reuse | Non-negotiable boundary |
|---|---|---|
| Return identity and amount | `returns(return_id, order_id, product_id, return_date, refund_amount, return_reason_code)`; `FictionStore.refund(return_id)` | One **return**, never a customer-wide query by guessed name; `processed_by` and customer PII are not needed |
| Order | `orders(order_id, total_amount, order_status)`; `FictionStore.order(order_id)` | Recorded order value is not payment settlement |
| Product lines | `order_items(order_item_id, order_id, product_id, quantity, unit_price, discount_pct)` | A return has **no `order_item_id` and no returned quantity**. All matching product lines are an **upper/reference comparison**, not the value of the actually returned units |
| Time | `return_date`; order-level `shipments.delivered_date` if needed to discuss timing | Return date does **not** establish request-submitted/received timestamp, specific item's delivery, item condition or return-policy eligibility |
| Return policy | `knowledge_documents` for **exact** `policy_id=FR-RET-2026-10-04`; local original Markdown with verified SHA | Effective **[2026-10-04, 2026-11-03)**, `Asia/Ho_Chi_Minh`. No `returns_policies` table; avoid guessed or fuzzy applicability |
| Data release | `data/fiction/manifest.json` plus local `fiction_retail.sqlite` verified by `FictionStore.open` | Pinned `fiction-retail-unified-v1.0.0`; no legacy `EL-###`/VND/source fallback, no Supabase runtime dependency |

**Reconciliation calculation (USD, integer cents or `Decimal` rounded only at the documented monetary boundary):**

- `order_amount = orders.total_amount`; `product_lines_net = Σ(quantity * unit_price * (1 - discount_pct / 100))` over **all** order lines with the exact returned `product_id`.
- `refund_amount = returns.refund_amount`; keep `refund_minus_order` and `refund_minus_product_lines` as signed differences for explanation.
- Match Fiction's independent source-audit flags using the **USD 0.01 tolerance**: `ABOVE_ORDER_RECONCILIATION` iff `refund_amount > order_amount + 0.01`; `ABOVE_PRODUCT_LINES_RECONCILIATION` iff `refund_amount > product_lines_net + 0.01`. No flag means **no anomaly on these two checks only**, not “refund valid/paid.”
- The existing `FictionStore.refund()` returns strict `refund_above_order_value` / `refund_above_returned_product_lines` comparisons **without** the +0.01 tolerance. Do **not** silently equate these booleans with the source-audit exception counts; implement a small reviewed reconciliation mapping only when needed and test threshold boundaries.
- Do not join `returns` to `order_items` and then sum `refund_amount` across multiplied rows. If one order/product has multiple separate returns, preserve each `return_id` and avoid double-counting when reporting totals.
- Missing order/product line, invalid money/discount/quantity, mixed identity or conflicting source version yields a scoped limitation or denial; missing evidence is **not zero**.

**Observed baseline:** released `returns` has **11,934** rows. The Fiction source audit and pinned RetailIQ manifest report **140** return amounts above order value (+$0.01) and **350** above returned product's aggregate order-line value (+$0.01). The sets may overlap. These published aggregates provide an **oracle target**, not evidence that UC-02 chat/agent paths have been implemented or run.

## 4. Result and verification contract

Reuse the existing answer/evidence envelope (`answer`, `records`, `contexts`, `request_id`) and Review 08/10's source/evidence fitness semantics; do not introduce a parallel response schema.

| Situation | Verified finding | Business disposition / limitation |
|---|---|---|
| Source-valid return, one or both +$0.01 anomaly flags | Return/order/product-line amounts, exact USD differences, row IDs | **NEEDS_REVIEW** for financial reconciliation; not proof of bad payment, fraud or return rejection |
| No two defined anomaly flags | Amounts agree **within the two tested comparisons** | **SUPPORTED** scoped observation only; `PAYMENT_STATUS_UNKNOWN`, `RETURN_ELIGIBILITY_UNVERIFIED` |
| Missing matched product line, ambiguous return scope or missing authoritative source | Partial order/return facts only, if verified | **INSUFFICIENT_EVIDENCE** for affected claim; ask for missing evidence rather than calculate from zero |
| Policy outside validity, unavailable/changed hash, unknown delivery/item condition | Numerical facts still allowed if source-valid | No policy eligibility conclusion; expose `POLICY_NOT_APPLICABLE_OR_UNVERIFIED` |
| Tool/model timeout, invalid ID, bad plan, cross-session reference | No trustworthy completed business conclusion | Execution error / clarification; no fabricated refund decision |

**Evidence refs:** `returns/<return_id>`, `orders/<order_id>`, `order_items/<order_item_id>`, optional verified `knowledge_documents/<document_id>` and `FR-RET-2026-10-04`; include release checksum, exact USD reference basis and relevant date. No customer phone/email/name. Distinguish **execution success**, **evidence fitness** and **business disposition**; never infer authorized human approval.

**Session and UI:** only inherit a `return_id` from **committed, same-session verified evidence** (#22). Return-specific follow-ups retain the correct order and product; “đã trả tiền chưa?” must answer that **settlement cannot be verified**. Existing React workspace presents actual findings, source IDs, limitations and observed execution events (#30), not an invented payment workflow.

## 5. Acceptance scenarios (design, not executed)

| Scenario | Independent expected oracle / important negative |
|---|---|
| **UC02-G1: above-order return** | Select a real pinned-release `return_id` via independent SQL `refund_amount > total_amount + 0.01`; assert row IDs, precise differences, `ABOVE_ORDER_RECONCILIATION`, `NEEDS_REVIEW` and no payment claim |
| **UC02-G2: above-product-line return** | Select a real `return_id` with refund greater than matching product-line net + 0.01; do not mistake multiple order lines/returns for returned quantity |
| **UC02-G3: no exception on both comparisons** | Independent SQL agrees to USD cents; return *scoped* normal finding but refuse to certify settlement or policy eligibility |
| **UC02-G4: aggregate reconciliation** | Real pinned release independently yields **140** and **350** flags by distinct `return_id`, never SUM on multiplied joins; sample oracle IDs recorded at execution, not fabricated in docs |
| **UC02-F1: unavailable/inconsistent source** | No matching order/product line, mismatched product/order, malformed source money or invalid discount → fail closed / `INSUFFICIENT_EVIDENCE` |
| **UC02-F2: financial edge** | Equal and exactly +$0.01 boundaries, repeated returns for same product/order, several matching product lines → deterministic cent-safe result without duplication |
| **UC02-F3: policy / temporal** | Return outside effective interval, mismatched doc hash, missing document, uncertain item condition / submission date → no eligibility or current-policy assertion |
| **UC02-F4: agent/session/transport** | Forged return ID in model plan, cross-session reference, tool/LLM timeout or stream disconnect → safe stop, no leaked PII, no unverified saved answer |

The live release's explicit IDs and expected cent amounts are **to be selected and recorded by the independent SQLite oracle** in the implementation PR; this design does not pretend to have queried the 199 MiB local binary.

## 6. Integration order and evidence gates

1. **Deterministic domain slice:** reuse `FictionStore.refund()` and `order()`, add only necessary fixed reconciliation semantics (+$0.01 rule, missing-evidence classification), test G1–G4 and F1–F3 against the **pinned real SQLite** plus focused adversarial fixtures. A source/SQL PASS is **not** an agent PASS.
2. **Bounded agent slice:** reuse #23/#22 to wire one `return_id` request and one same-session follow-up to existing `/ask`/`/ask/stream`; compare *actual* tool inputs, data and output with the independent oracle. Avoid a new `RefundAgent` unless the existing specialist path proves inadequate.
3. **Explanation / UI / transport:** optional exact filtered policy RAG (#27) **only** when useful, shared MCP (#26) only if an actual tool-boundary requirement warrants it, existing evidence and UI (#28/#30), no fictional HITL/payment actions.
4. **E2E acceptance:** provider-backed turn(s), real trace, browser evidence and negative cases; record SHA, Fiction release/db checksum, mode, request + `return_id`, independent expected vs observed USD amounts, tool invocations, trace IDs, and explicit remaining gaps. Only then update owner Issue evidence/status.

**Stop condition:** if the source cannot establish approval, payment settlement, return-item quantity or policy eligibility, report that limitation and terminate **without** building a fake subsystem to fill the gap. **No feature-code change is part of this design PR.**
