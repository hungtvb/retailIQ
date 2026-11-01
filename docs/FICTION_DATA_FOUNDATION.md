# Fiction Retail — Data Foundation v1

**Decision:** Fiction Retail E-Commerce is the canonical **historical** business dataset. The old 10-product `EL-###` fixture is retired as a business source, but legacy runtime code is not yet removed. This change introduces a read-only SQL boundary and a reproducible, source-linked RAG corpus; **chat/API, LangGraph and live Chroma retrieval have not been cut over**.

## Source

Download the [Fiction Retail dataset](https://www.kaggle.com/datasets/nasalakshay/fiction-retail-e-commerce-dataset), and keep `fiction-retail.db` locally at `data/fiction-retail.db`. Never commit the raw database, corpus, or generated reports.

Validated source SHA-256: `9f95373e46219e880ae54f995b6f2c2c439c3746e500e484fe3ab2bf9ac55754`.

The 10-table source contains 5,000 products, 150,000 orders, 346,202 order items, 11,476 inventory records, 119,936 shipments and 11,934 returns. It models a **multi-category** retailer in **USD**. Orders cover 2023-01-01 to 2024-04-30; it is not a live data feed.

## Business contracts

| Domain function | Semantic contract |
|---|---|
| `product(db, id)` | Exact UUID product identity; catalog facts only, not invented specifications |
| `stock(db, id)` | On-hand minus reserved by warehouse. `last_restocked_date` is not a source refresh time |
| `top_sellers(db, period)` | Delivered-order units by calendar month, stable UUID tie-break; provisional status policy |
| `delivered_merchandise_value(db, period[, id])` | USD line value after discount; **before** returns/tax/shipping, **not** financial net revenue |
| `return_reasons(db, period[, id])` | Return-event counts by return date and reason code, not observed customer sentiment |

Queries use prepared parameters, input checks and SQLite read-only connections. The existing VND / `completed` definitions must not be used on Fiction.

## Source-linked RAG corpus

```sh
python -m scripts.build_fiction_rag --source data/fiction-retail.db --output data/fiction_rag_v1 --category electronics --max-products 60 --max-reviews 100 --max-tickets 60

python -m scripts.verify_fiction_rag --source data/fiction-retail.db --corpus data/fiction_rag_v1 --report data/fiction_rag_verification.json
```

The output includes catalog-derived Markdown, **synthetic** review examples, **synthetic** after-sales support examples, `records.jsonl` containing source-linked IDs, and a provenance manifest. No observed review ratings, product manuals, warranties, or actual support resolutions exist in Fiction. Do not present the generated narratives as factual customer feedback.

This corpus deliberately stays outside `data/product_docs` and `data/knowledge` until the RAG indexer supports exact `product_id`/`kind` metadata filtering and strict source isolation; otherwise it could mix Fiction UUIDs with retired `EL-###` documents.

## Evidence and open gates

```sh
RETAILIQ_FICTION_DB=data/fiction-retail.db python -m pytest -q tests/test_fiction_data_foundation.py
```

Local verification on the uploaded snapshot found delivered merchandise value for April 2024: **18,571,791.10 USD**, and reproduced the historical source counts. The separate 220-document source-linked corpus verification returned PASS. These are **offline data tests**, not LLM/RAG, real-time inventory or authenticated action approval.

**Next PR**: migrate chat/SQL tools, session product identity and RAG index namespace to Fiction, remove legacy entry points, enforce retrieval metadata constraints, and run independent HTTP/conversation acceptance. Do not label the app as Fiction-powered until this gate passes.
