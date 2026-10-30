# RetailIQ — Business Query Acceptance Audit

**Goal:** Test business expectations against the existing implementation *before* deciding what to fix. Predictions are derived from code inspection; **only the executable report shows observed PASS/FAIL/ERROR**.

| Case IDs | Expected behavior | Initial code-based hypothesis |
| --- | --- | --- |
| CAT-01–05 | Correct most/least expensive product, VND price (VI/EN) | Likely FAIL: no price-ranking route/query |
| CAT-06 | Price of explicitly identified AlphaBook Pro 14 | Likely PASS: direct catalog lookup |
| CAT-07 | Cheapest product in Accessory category | Likely FAIL: category filtering unavailable |
| SALES-01–02 | Correct October/September net revenue from completed orders | Likely PASS |
| SALES-03 | Exactly five top-selling products in correct rank | Likely PASS |
| SALES-04 | Exactly three top-selling products | Likely FAIL: fixed top-5 SQL limit |
| STOCK-01–02 | Correct known-SKU available stock / clarification if unknown | Likely PASS |
| CROSS-01–02 | All five top-selling SKUs joined to available stock | Likely FAIL: single-SKU inventory path |
| CTX-01 | Sales-to-Inventory handoff for the highest seller | Likely PASS |
| CTX-02 | Revenue follow-up for prior month | Likely PASS |
| CTX-03 | “Các sản phẩm đó” refers to all five September top sellers | Likely FAIL: context reduced to one SKU |
| CTX-04 | “Đứng thứ 2” resolves September ranking, not today's top seller | Likely FAIL: rank/period not preserved |
| RAG-01 | Product spec answer includes source evidence | Likely PASS with relevant indexed docs |

## Run locally

Use the Python environment that runs RetailIQ, from the repository root:

```bash
python -m pip install -r requirements-offline.txt
python -m scripts.audit_queries
```

The script uses a **temporary SQLite fixture and temporary chat/checkpoint databases**. It fixes the reference date to **2026-10-28** so SQL expectations are reproducible; your existing `data/retailiq.sqlite3`, chats, and knowledge documents are untouched. It executes the actual `POST /ask` application route, using the offline backend by default.

Results are printed with failure layers and saved to the gitignored `data/query_audit_report.json`. The default audit is *observational* and exits successfully even when business cases fail; add `--strict` to make any FAIL/ERROR return a nonzero status.

**Optional real-provider validation** (uses configured .env, model/embeddings, Chroma and can cost tokens):

```bash
python -m pip install -r requirements-full.txt
python -m scripts.index_products
python -m scripts.audit_queries --mode full --ids CAT-01,CAT-03,CROSS-01,CTX-01 --confirm-live
```

Start with just these four cases to limit cost. Full mode requires credentials and indexed documents. It still uses temporary chat/retail/checkpoint SQLite databases. Neither offline results nor mocked unit tests prove provider-backed Agent execution.

## Interpreting the report

- **PASS:** the actual API answer and SQL records satisfy the independent business reference calculation.
- **FAIL:** request completed but result is wrong or incomplete. Compare `expected`, `observed`, and `suspected_layer`.
- **ERROR:** dependency/provider/index/API execution failed; look in execution logs before blaming business routing.
- **Hypothesis != observed outcome:** revise the hypothesis, not the application, until the root cause is verified.

**Boundaries:** the checker covers 20 chosen questions, not arbitrary natural-language understanding. It does not alter RetailIQ business logic, add agents, or test real retailer data. Do not claim any untested business benefit.
