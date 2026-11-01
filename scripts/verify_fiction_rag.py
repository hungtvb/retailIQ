"""Read-only validation for source-linked Fiction Retail RAG documents.

Validates exact IDs and source provenance, not embeddings or customer sentiment.
"""
from __future__ import annotations

import argparse
from contextlib import closing
import hashlib
import json
from pathlib import Path
import re
import sqlite3

EMAIL = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")


def file_sha(path: Path) -> str:
    dig = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            dig.update(chunk)
    return dig.hexdigest()


def verify(source: Path, corpus: Path) -> dict:
    source = source.resolve()
    corpus = corpus.resolve()
    manifest = json.loads((corpus / ".generation_manifest").read_text(encoding="utf8"))
    assert file_sha(source) == manifest["source_sha256"], "Source checksum mismatch"
    records = [json.loads(x) for x in (corpus / "records.jsonl").read_text(encoding="utf8").splitlines()]
    assert len(records) == manifest["metadata_records"]
    assert len({r["document_id"] for r in records}) == len(records)
    assert len({r["path"] for r in records}) == len(records)
    counts = {"products": 0, "reviews": 0, "support_tickets": 0}
    distinct = {"product_catalog": set(), "customer_review": set(), "support_ticket": set()}
    errors = []
    source_conn = sqlite3.connect(source.as_uri() + "?mode=ro", uri=True)
    with closing(source_conn) as src:
        src.backup(db := sqlite3.connect(":memory:"))
        with closing(db):
            db.executescript("""
              CREATE INDEX v_products ON products(product_id);
              CREATE INDEX v_orders ON orders(order_id);
              CREATE INDEX v_items ON order_items(order_id,product_id,order_item_id);
              CREATE INDEX v_returns ON returns(return_id,order_id,product_id);
            """)
            for r in records:
                kind, pid = r["kind"], r["product_id"]
                if kind not in distinct:
                    errors.append(f"Bad kind: {kind}"); continue
                distinct[kind].add(pid)
                try:
                    path = (corpus / r["path"]).resolve()
                    assert path.is_relative_to(corpus) and path.is_file()
                    body = path.read_text(encoding="utf-8")
                    assert f"Product ID: {pid}\n" in body
                    assert not EMAIL.search(body)
                    assert "Customer ID:" not in body and "Customer name:" not in body
                    p = db.execute("SELECT name,category,brand,price,weight_kg FROM products WHERE product_id=?", (pid,)).fetchone()
                    assert p is not None, "Unknown product"
                    if kind == "product_catalog":
                        counts["products"] += 1
                        assert r["is_synthetic_text"] is False
                        assert f"Product name: {p[0]}\n" in body
                        assert f"Brand: {p[2]}\n" in body
                        assert f"Category: {p[1]}\n" in body
                        assert "not provided by the source" in body
                    else:
                        assert r["is_synthetic_text"] is True
                        assert "Synthetic Text: true" in body
                        order = db.execute("SELECT order_status FROM orders WHERE order_id=?", (r["order_id"],)).fetchone()
                        assert order is not None, "Unknown order"
                        assert db.execute("SELECT 1 FROM order_items WHERE order_id=? AND product_id=?",
                                          (r["order_id"],pid)).fetchone(), "Order-product mismatch"
                        if r.get("order_item_id"):
                            assert db.execute("SELECT 1 FROM order_items WHERE order_id=? AND product_id=? AND order_item_id=?",
                                              (r["order_id"],pid,r["order_item_id"])).fetchone(), "Order item mismatch"
                        if kind == "customer_review":
                            counts["reviews"] += 1
                            assert "not an observed customer review" in body
                            assert "generated_synthetic_review_from_fiction_order" in body
                        else:
                            counts["support_tickets"] += 1
                            assert db.execute("SELECT 1 FROM returns WHERE return_id=? AND order_id=? AND product_id=?",
                                              (r["return_id"],r["order_id"],pid)).fetchone(), "Ticket-return mismatch"
                            assert "no actual conversation or resolution recorded" in body
                except (AssertionError, KeyError, UnicodeError, OSError) as e:
                    errors.append(f"{r.get('document_id', '?')}: {str(e) or 'validation failure'}")
    if counts != manifest["counts"]:
        errors.append(f"Count mismatch: {counts} != {manifest['counts']}")
    if not distinct["customer_review"].issubset(distinct["product_catalog"]):
        errors.append("Review product is outside selected catalog")
    if not distinct["support_ticket"].issubset(distinct["product_catalog"]):
        errors.append("Support product is outside selected catalog")
    return {"status": "PASS" if not errors else "FAIL", "source_sha256": manifest["source_sha256"],
            "validated_documents": len(records), "by_kind": counts,
            "distinct_products_by_kind": {k: len(v) for k,v in distinct.items()},
            "errors": errors[:20], "limitations": ["No actual review or support content exists in Fiction",
                         "This verifies lineage and labels, not RAG faithfulness or sentiment accuracy"]}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--source", type=Path, required=True)
    p.add_argument("--corpus", type=Path, required=True)
    p.add_argument("--report", type=Path)
    args = p.parse_args()
    report = verify(args.source,args.corpus)
    if args.report:
        args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2),encoding="utf8")
    print(json.dumps(report,ensure_ascii=False,indent=2))
    if report["status"] != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
