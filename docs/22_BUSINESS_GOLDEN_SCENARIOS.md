# RetailIQ — Business Golden Scenarios (UC-01)

**Selected problem:** Inventory & Sales Decision Support. **Evidence:** synthetic-data automated business-contract tests, not a real retailer user study.

**Acceptance owner:** BA/Domain Analyst + QA (proposed). **PO/domain sign-off:** pending.

## Business decision contract

UC-01 is not merely “a chatbot responds.” The workflow must: identify the top seller from completed orders in the configured month; verify the exact same SKU in inventory; calculate available = on_hand − reserved by location; compare total available with completed units sold; and return a traceable *human replenishment review* outcome. No purchase order, inventory mutation, demand forecast or automated procurement is implied.

**Demo screening heuristic:** flag for human review iff total available < monthly completed units sold. This is not a production reorder point. Lead time, inbound supply, returns, target service level, demand forecast and maximum stock age are not modeled.

## Test-only synthetic data

The suite uses a dedicated temporary SQLite file, separate from the main 10-product and 120-order seed fixture.

| SKU | Product | Oct completed units | Warehouse available | Store available | Total available | Expected result |
|---|---|---:|---:|---:|---:|---|
| SKU-A | Alpha Laptop | 20 | 4 on-hand - 2 reserved = 2 | 5 - 2 = 3 | **5** | **REVIEW** |
| SKU-B | Beta Charger | 8 | 9 - 2 = 7 | 6 - 1 = 5 | **12** | No immediate priority |
| SKU-C | Gamma Keyboard | 4 | Missing | Missing | **Unknown, not zero** | Abstain if selected |

Sales truth table: SKU-A = 20 × 100,000 − 20,000 = **1,980,000 VND** (online); SKU-B = 8 × 50,000 − 10,000 = **390,000 VND** (store); SKU-C = 4 × 30,000 = **120,000 VND** (online). Total = **2,490,000 VND** (online 2,100,000, store 390,000). Cancelled, September 30, and November 1 orders each contain **999 units** to expose invalid filters.

## Business golden scenario register

| ID | Situation | Exact expectation |
|---|---|---|
| G01 | Top SKU-A sold 20, available 5 | REVIEW, correct two-location and sold evidence |
| G02 | SKU-A available 19 | REVIEW |
| G03 | SKU-A available exactly 20 or 21 | No immediate priority (strictly less comparison) |
| G04 | Remove SKU-A inventory rows | Abstain due to missing inventory; do not invent zero |
| G05 | Reserved exceeds on-hand on SKU-A | Safe API failure, no confident recommendation |
| G06 | No completed orders | No top seller or replenishment recommendation invented |
| G07 | Cancelled/out-of-period orders, discounts | Exact 2,490,000 VND revenue, 20/8/4 ranking and channel totals |
| G08 | SKU-B ties SKU-A on 20 units | Stable SKU-A, then SKU-B ordering |
| G09 | Unknown SKU or two matching product names | Request clarification, no arbitrary product selection |
| G10 | SKU-A across warehouse and store | Correct total 2+3=5 and per-location evidence |
| G11 | Change reference month to December | October not reused; January boundary calculated correctly |
| G12 | Completed-order line references missing product | Fail closed, not a fabricated decision |
| G13 | Repeated business API questions | Source retail fixture checksum unchanged |
| G14 | Stock timestamp is old (2025) | **Known gap:** Week 1 accepts old timestamp; freshness-aware rejection deferred to Week 2 |

There are **14 scenario IDs** and multiple parameterized threshold variations. The code is in tests/test_business_golden_scenarios.py.

## How to run

Install requirements-offline.txt with Python 3.11+, then:

~~~bash
python -m pytest -q -rs tests/test_business_golden_scenarios.py
~~~

For the full suite and additional localhost E2E:

~~~bash
RETAILIQ_REQUIRE_LANGGRAPH=true python -m pytest -q -rs
node --test tests/frontend_format.test.cjs
python -m scripts.quality_gate --samples 50
~~~

The golden suite tests real SQLite arithmetic, FastAPI request handling and offline deterministic business rules. External model and retrieval providers are **not** used. Refer to CI results for the exact tested commit; do not claim live LLM correctness from a mocked/deterministic run.

## Acceptance and open business issues

- **Engineering gate:** verify business outputs, data source/period selection, stable SKU identity, correct arithmetic and no inventory write side effects.
- **Human decision gate:** a result is a *review flag* only and must not create orders or claim a demand forecast.
- **Missing-data gate:** if no trustworthy stock/sales evidence exists, abstain or fail closed.
- **Freshness gate:** **NOT IMPLEMENTED** in Week 1; G14 documents observed behavior, not an accepted freshness SLA. Stale inventory must be labeled as a known limitation.
- **Business value gate:** no measured manual baseline, assisted baseline, reviewer usefulness, or validated reduction in time-to-insight exists. Persona/PO review and success criteria remain pending.

## Three-minute business demo

Ask the single replenishment question, show the verified top seller and stock rows; demonstrate a sufficient-stock alternative; demonstrate abstention on missing inventory; explain why cancelled/outside-month orders are excluded; close with the known freshness limitation and human approval boundary.

References: [Business Scope](21_INVENTORY_SALES_BUSINESS_SCOPE.md), [Data/KPI Contract](13_Data_and_API_Contract.md), [Local E2E/Benchmark](20_LOCAL_E2E_BENCHMARK_EVIDENCE.md).
