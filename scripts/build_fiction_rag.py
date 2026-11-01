"""Build provenance-labelled RetailIQ RAG documents from Fiction Retail SQLite.

Does not alter the source database or present generated reviews as actual user data.
Run after downloading `fiction-retail.db` from its published CC0 source.
"""
from __future__ import annotations

import argparse
from contextlib import closing
import hashlib
import json
from pathlib import Path
import re
import sqlite3

ROOT = Path(__file__).resolve().parents[1]
SOURCE_URL = "https://www.kaggle.com/datasets/nasalakshay/fiction-retail-e-commerce-dataset"
GENERATOR_VERSION = "fiction-rag-v2-source-linked"
ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")


def _safe_id(value: object) -> str:
    if not isinstance(value, str) or not ID.fullmatch(value):
        raise ValueError("Invalid source identifier; cannot create a document path")
    return value


def _text(value: object) -> str:
    # Markdown content is source data, not instructions; remove control chars and
    # embedded newlines to prevent a field from impersonating another field.
    if value is None:
        return "not recorded"
    return re.sub(r"\s+", " ", str(value)).strip().replace("<", "‹").replace(">", "›")[:180]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _require_columns(db: sqlite3.Connection, table: str, required: set[str]) -> None:
    actual = {r[1] for r in db.execute(f"PRAGMA table_info({table})")}
    missing = required - actual
    if missing:
        raise ValueError(f"Unsupported Fiction schema in {table}: {sorted(missing)}")


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        raise ValueError(f"Refusing overwrite: {path}")
    path.write_text(content, encoding="utf-8")


def _review_text(return_reason: str | None, index: int) -> tuple[int, str]:
    if return_reason:
        return 2, ("Synthetic customer scenario: I requested a return for this purchase. "
                   "The linked return record lists the reason as '" + _text(return_reason) +
                   "'. This sentence is GENERATED, not a customer quotation.")
    variants = [
        "Synthetic customer scenario: The product name matches my order. I am still evaluating it.",
        "Synthetic customer scenario: I would appreciate a clearer setup guide. I cannot yet assess durability.",
        "Synthetic customer scenario: The ordering process was straightforward; long-term quality is unknown.",
    ]
    return (3 if index % 3 != 2 else 4), variants[index % len(variants)]


def generate(source: Path, output: Path, *, max_products: int = 200,
             max_reviews: int = 120, max_tickets: int = 100,
             category: str | None = None) -> dict:
    """Create a fresh, reproducible corpus. Limits 0 mean 'no limit' for products.

    Reviews and ticket conversations are synthetic scenarios. Transactional
    links are checked against the source database; there are no invented SKUs,
    orders, customers, warranties, defect rates, refund outcomes, or delivery SLAs.
    """
    source = source.expanduser().resolve()
    output = output.expanduser().resolve()
    if not source.is_file():
        raise FileNotFoundError(f"Fiction SQLite source not found: {source}")
    if max_products < 0 or max_reviews < 0 or max_tickets < 0:
        raise ValueError("Limits cannot be negative")
    if category is not None and (not category.isascii() or not re.fullmatch(r"[a-z_]{2,40}", category)):
        raise ValueError("Invalid category filter")
    if output.exists() and not output.is_dir():
        raise ValueError("Output path is not a directory")
    if output.exists() and any(output.iterdir()):
        raise ValueError("Output must be a fresh/empty folder; do not overwrite an existing RAG corpus")
    if output == source.parent or output.is_relative_to(source):
        raise ValueError("Output cannot be the source database")

    # The published 95 MiB SQLite has no declared indexes or FK constraints.
    # Make an isolated in-memory copy for efficient JOINs and safe validation;
    # the supplied database stays read-only throughout this operation.
    uri = source.as_uri() + "?mode=ro"
    with closing(sqlite3.connect(uri, uri=True)) as source_db, closing(sqlite3.connect(":memory:")) as db:
        source_db.backup(db)
        db.row_factory = sqlite3.Row
        _require_columns(db, "products", {"product_id", "name", "brand", "category", "price", "weight_kg"})
        _require_columns(db, "orders", {"order_id", "customer_id", "order_status"})
        _require_columns(db, "order_items", {"order_item_id", "order_id", "product_id"})
        _require_columns(db, "returns", {"return_id", "order_id", "product_id", "return_reason_code"})
        db.executescript("""
            CREATE INDEX idx_rag_orders_id ON orders(order_id);
            CREATE INDEX idx_rag_products_id ON products(product_id);
            CREATE INDEX idx_rag_items_order_product ON order_items(order_id, product_id);
            CREATE INDEX idx_rag_items_product ON order_items(product_id);
            CREATE INDEX idx_rag_returns_order_product ON returns(order_id, product_id);
            CREATE INDEX idx_rag_returns_product ON returns(product_id);
            CREATE INDEX idx_rag_products_category ON products(category);
        """)
        # Validate return lineage rather than silently dropping corrupt returns.
        bad_returns = db.execute("""
            SELECT COUNT(*) FROM returns AS r
            WHERE NOT EXISTS (SELECT 1 FROM orders o WHERE o.order_id=r.order_id)
               OR NOT EXISTS (SELECT 1 FROM products p WHERE p.product_id=r.product_id)
               OR NOT EXISTS (SELECT 1 FROM order_items oi
                              WHERE oi.order_id=r.order_id AND oi.product_id=r.product_id)
        """).fetchone()[0]
        if bad_returns:
            raise ValueError(f"Source contains {bad_returns} returns without valid order-product lineage")
        # Choose returned products first: this focused corpus then supports
        # Product→Review→Return→Support questions for the SAME product IDs.
        # 'category' may be None for cross-category sampling.
        clause = "WHERE p.category=? " if category else ""
        params = (category,) if category else ()
        product_sql = ("SELECT p.product_id,p.name,p.brand,p.category,p.price,p.weight_kg "
                       "FROM products p " + clause +
                       "ORDER BY CASE WHEN EXISTS (SELECT 1 FROM returns r "
                       "WHERE r.product_id=p.product_id) THEN 0 ELSE 1 END, p.product_id" +
                       (" LIMIT ?" if max_products else ""))
        products = [dict(row) for row in db.execute(
            product_sql, params + ((max_products,) if max_products else ()))]
        if not products:
            raise ValueError("No products with valid return evidence for the selected category")
        product_ids = {_safe_id(p["product_id"]) for p in products}
        if len(product_ids) != len(products):
            raise ValueError("Duplicate product identifiers")
        args = tuple(sorted(product_ids))
        placeholders = ",".join("?" for _ in args)
        returned = [dict(row) for row in db.execute(f"""
            SELECT r.return_id, r.order_id, r.product_id, r.return_reason_code,
                   MIN(oi.order_item_id) AS order_item_id,
                   COUNT(DISTINCT oi.order_item_id) AS matching_line_count
            FROM returns r JOIN orders o ON o.order_id=r.order_id
            JOIN order_items oi ON oi.order_id=r.order_id AND oi.product_id=r.product_id
            WHERE r.product_id IN ({placeholders})
            GROUP BY r.return_id, r.order_id, r.product_id, r.return_reason_code
            ORDER BY r.return_id
        """, args)]
        # Only one order-item can be claimed as the specific purchased line.
        # The (order_id, product_id) association is still verified for multiples.
        for row in returned:
            if row["matching_line_count"] != 1:
                row["order_item_id"] = None
        delivered = [dict(row) for row in db.execute(f"""
            SELECT oi.order_item_id,oi.order_id,oi.product_id
            FROM order_items oi JOIN orders o ON o.order_id=oi.order_id
            WHERE oi.product_id IN ({placeholders})
              AND o.order_status='delivered'
              AND NOT EXISTS (SELECT 1 FROM returns r
                              WHERE r.order_id=oi.order_id AND r.product_id=oi.product_id)
            ORDER BY oi.order_item_id
            LIMIT ?
        """, args + (max_reviews,))]
        source_counts = {table: db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                         for table in ("products", "orders", "order_items", "returns")}

    # Breadth-first selection: one return per product before a second return
    # for the same product. This produces useful cross-product RAG coverage.
    groups = {pid: [] for pid in sorted(product_ids)}
    for value in returned:
        groups[value["product_id"]].append(value)
    returned_balanced = []
    while any(groups.values()):
        for pid in sorted(groups):
            if groups[pid]:
                returned_balanced.append(groups[pid].pop(0))

    # All source reads succeed before creating generated content.
    output.mkdir(parents=True, exist_ok=True)
    counts = {"products": 0, "reviews": 0, "support_tickets": 0}
    records = []
    for p in products:
        pid = _safe_id(p["product_id"])
        body = (f"# Catalog product: {_text(p['name'])}\n"
                f"Document Kind: product_catalog\nProduct ID: {pid}\n"
                "Provenance: fiction_retail_catalog_derived\n"
                "Synthetic Text: false; catalog values copied from synthetic Fiction Retail source\n"
                f"Product name: {_text(p['name'])}\nBrand: {_text(p['brand'])}\n"
                f"Category: {_text(p['category'])}\nList price (USD): {_text(p['price'])}\n"
                f"Weight (kg): {_text(p['weight_kg'])}\n"
                "Technical specifications, warranty terms, compatibility and user manual: not provided by the source. "
                "Do not infer these or live inventory from this document.\n")
        relative = f"products/{pid}.md"
        _write(output / relative, body)
        records.append({"document_id": "catalog:" + pid, "path": relative,
                        "kind": "product_catalog", "product_id": pid,
                        "provenance": "catalog_derived", "is_synthetic_text": False})
        counts["products"] += 1

    # Use a mix of transaction-linked return scenarios and neutral delivered
    # order scenarios; never present generated sentiment as observed reviews.
    selected = []
    for r in returned_balanced:
        if len(selected) >= (max_reviews + 1) // 2:
            break
        selected.append((r, r["return_reason_code"]))
    for r in delivered:
        if len(selected) >= max_reviews:
            break
        selected.append((r, None))
    for i, (r, reason) in enumerate(selected, 1):
        pid = _safe_id(r["product_id"])
        _safe_id(r["order_id"])
        if r.get("order_item_id") is not None:
            _safe_id(r["order_item_id"])
        rating, body = _review_text(reason, i)
        relative = f"reviews/review-{i:05d}.md"
        _write(output / relative,
               f"# Simulated post-purchase review {i:05d}\n"
               f"Document Kind: customer_review\nProduct ID: {pid}\n"
               f"Order ID: {r['order_id']}\nOrder Item ID: {r['order_item_id'] or 'ambiguous_multiple_matching_order_lines'}\n"
               "Provenance: generated_synthetic_review_from_fiction_order\n"
               "Synthetic Text: true; not an observed customer review\n"
               f"Simulated rating (1-5): {rating}\n"
               f"Review: {body}\n")
        records.append({"document_id": f"review:{i:05d}", "path": relative,
                        "kind": "customer_review", "product_id": pid,
                        "order_id": r["order_id"], "order_item_id": r.get("order_item_id"),
                        "provenance": "generated_synthetic_review", "is_synthetic_text": True})
        counts["reviews"] += 1

    for i, r in enumerate(returned_balanced[:max_tickets], 1):
        pid = _safe_id(r["product_id"])
        for key in ("order_id", "return_id"):
            _safe_id(r[key])
        if r.get("order_item_id") is not None:
            _safe_id(r["order_item_id"])
        relative = f"support/ticket-{i:05d}.md"
        _write(output / relative,
               f"# Simulated after-sales case {i:05d}\n"
               f"Document Kind: support_ticket\nProduct ID: {pid}\n"
               f"Order ID: {r['order_id']}\nOrder Item ID: {r['order_item_id'] or 'ambiguous_multiple_matching_order_lines'}\n"
               f"Return ID: {r['return_id']}\n"
               "Provenance: generated_synthetic_support_from_fiction_return\n"
               "Synthetic Text: true; no actual conversation or resolution recorded\n"
               f"Recorded return reason code: {_text(r['return_reason_code'])}\n"
               "Simulated customer message: Please help me understand the status of my return request.\n"
               "Simulated support reply: We will review the existing return record. "
               "No delivery SLA, refund completion or case resolution can be inferred.\n")
        records.append({"document_id": f"support:{i:05d}", "path": relative,
                        "kind": "support_ticket", "product_id": pid,
                        "order_id": r["order_id"], "order_item_id": r.get("order_item_id"),
                        "return_id": r["return_id"],
                        "provenance": "generated_synthetic_support", "is_synthetic_text": True})
        counts["support_tickets"] += 1

    manifest = {"generator": GENERATOR_VERSION, "source_url": SOURCE_URL,
                "source_sha256": _sha256(source), "source_file": source.name,
                "source_counts": source_counts, "category_filter": category,
                "corpus_path": str(output), "counts": counts,
                "limits": {"products": max_products, "reviews": max_reviews, "tickets": max_tickets},
                "return_lineage_invalid": bad_returns,
                "source_schema_status": "validated_for_selected_columns_and_return_lineage",
                "review_and_ticket_origin": "synthetic_not_real_customer_feedback",
                "product_document_origin": "derived_only_from_catalog_fields",
                "limitations": ["no_source_product_specs_or_warranty", "no_genuine_customer_reviews",
                                "no_actual_support_transcript", "no_liveness_guarantee"]}
    # Metadata is deliberately separate from the text so future retrieval can
    # apply exact product_id/kind filtering. .jsonl is not a supported extension
    # in the existing Markdown/JSON/PDF document indexer.
    (output / "records.jsonl").write_text(
        "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in records),
        encoding="utf-8")
    manifest["metadata_records"] = len(records)
    manifest["sampled_product_ids_with_reviews"] = len({r["product_id"] for r in records if r["kind"] == "customer_review"})
    manifest["sampled_product_ids_with_support"] = len({r["product_id"] for r in records if r["kind"] == "support_ticket"})
    # Keep machine-readable manifest out of RAG docs to prevent indexing it as factual content.
    manifest_path = output / ".generation_manifest"
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True, help="Path to official Fiction Retail SQLite DB")
    parser.add_argument("--output", type=Path, default=ROOT / "data" / "fiction_rag_v1")
    parser.add_argument("--max-products", type=int, default=200, help="0 for whole product catalog")
    parser.add_argument("--category", type=str, default=None, help="Optional catalog category, e.g. electronics")
    parser.add_argument("--max-reviews", type=int, default=120)
    parser.add_argument("--max-tickets", type=int, default=100)
    args = parser.parse_args()
    print(json.dumps(generate(args.source, args.output, max_products=args.max_products,
                              max_reviews=args.max_reviews, max_tickets=args.max_tickets,
                              category=args.category),
                     ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()