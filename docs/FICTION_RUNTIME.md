# Fiction unified runtime — M0 boundary

**Status:** Issue [#31](https://github.com/hungtvb/retailIQ/issues/31): read-only data/SQL foundation only; **not** a chat, LangGraph, MCP, RAG or security migration. Do not interpret a local SQL PASS as Fiction E2E acceptance.

## Release and local setup

- Source: [Fiction Retail unified release](https://github.com/hungtvb/fiction-retail), `fiction-retail-unified-v1.0.0`, `main` `d92aa3fb28b9fb1b492fdc2e784b8cd4d49ebb72`.
- `data/fiction/manifest.json` is a committed **release-locked copy** of Fiction's upstream manifest. Update it only with a deliberate reviewed release upgrade.
- Obtain the **real LFS object** `data/fiction_retail.sqlite` from the Fiction repository (`git lfs pull`) or a byte-identical local copy, then put it in RetailIQ at `data/fiction/fiction_retail.sqlite`. Never commit the 199 MiB database through ordinary Git. No Supabase/cloud dependency at runtime.
- Run from repository root:

```sh
python -m scripts.verify_fiction_runtime \
  --db data/fiction/fiction_retail.sqlite \
  --manifest data/fiction/manifest.json
```

The verifier refuses a missing/wrong manifest or DB, mismatched SHA-256, row counts, embedded release metadata, broken FK/integrity, or a noncanonical UUID→SKU mapping. It also compares **independent read-only SQL oracles** for top sellers in October 2026, a no-snapshot case and an anomalous refund, plus time-scope and no-PII checks. It never repairs Fiction data.

## Implementation contract

Use `FictionStore.open(db_path, manifest_path)` from `retailiq.domain.fiction`. **Always** pass an explicit DB path and verified manifest: Fiction queries never fall back to the old `RETAILIQ_DATA_DB` / `EL-###` fixture. Shared low-level SQL adapter retains the legacy default for unrelated, not-yet-migrated application modules.

Allowed read operations: `resolve_product`, `product`, `order`, `inventory`, `top_sellers`, `refund`, `fulfillment_case`. Each returns bounded data plus canonical identifiers, source release checksum, scope, temporal context, record references and material limitations. The `query` adapter remains read-only, bounded and parameterized, not a user-supplied Text-to-SQL executor.

- **Identity:** `product_id` canonical UUID; SKU is a 1:1 reference, not a manufacturer identifier.
- **Time:** business reference is 2026-11-03 (Asia/Ho_Chi_Minh); transaction history was shifted by 916 days, not live. October calendar ranking is not the `sales_targets.month='2026-10'` cohort window. Flag partial first/last months rather than treating them as complete.
- **Money:** USD; `orders.total_amount` is recorded order value, **not settled revenue**. `refund_amount` is a recorded return amount, **not a completed payout**. Keep original `order_items.unit_price` and discounts separate from synthetic dated curated list prices.
- **Stock:** base `inventory` has no observation timestamp; `last_restocked_date` must not be shown as freshness. An absent row is **missing evidence**, not zero available stock.
- **Backorder:** 100 case-scoped investigations, not a full inventory ledger. `fulfillment_case` filters snapshot candidate inputs by case/product, known cutoff, observed/received time, 24h age, quantity and warehouse eligibility. It **does not authorize** a transfer or assert that a policy remains effective. Policy validity/corroboration and manager HITL are owned by [#28](https://github.com/hungtvb/retailIQ/issues/28) and [#29](https://github.com/hungtvb/retailIQ/issues/29).
- **Privacy:** no customer name, contact, address or payment method in returned orders, refund or traces; read-only functions do not mutate source tables.

## Acceptance boundary and dependencies

This module is intentionally **not connected to `/ask` or `/ask/stream`**. Wire it into conversation state via [#22](https://github.com/hungtvb/retailIQ/issues/22), orchestration via [#23](https://github.com/hungtvb/retailIQ/issues/23), MCP via [#26](https://github.com/hungtvb/retailIQ/issues/26), RAG via [#27](https://github.com/hungtvb/retailIQ/issues/27), evidence fitness via [#28](https://github.com/hungtvb/retailIQ/issues/28) and UI/E2E via [#30](https://github.com/hungtvb/retailIQ/issues/30). No new synthetic reviews/support-doc generator: use Fiction's original authored Markdown and document registry for RAG in #27.

Previous draft PRs [#24](https://github.com/hungtvb/retailIQ/pull/24) and [#25](https://github.com/hungtvb/retailIQ/pull/25) are closed as superseded. Their reusable ID/read-only SQL and negative scenario lessons informed this foundation; **their old source-only generator, 2024 date assumptions and deterministic chatbot path were not brought forward**.

### Evidence modes

- `pytest` small fixtures: offline contract/negative tests, **not real-data acceptance**.
- `verify_fiction_runtime` on the actual 209,063,936-byte database: **real local SQLite / independent SQL oracle**, no provider.
- LangGraph/MCP/RAG/LLM/Chromium acceptance: **not claimed**, tracked by owning issues. Record dataset SHA, commit, exact command and observed evidence before marking downstream CAP PASS.
