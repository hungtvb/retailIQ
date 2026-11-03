"""CLI and independent SQL oracle smoke for a local Fiction unified release.

No LLM, no LangGraph, no model-graded expected answers, no business writes.
"""
from __future__ import annotations
import argparse
from contextlib import closing
from decimal import Decimal
import json
from pathlib import Path
import sqlite3

from retailiq.domain.fiction import FictionStore, FictionDataError, verify_release


def _oracle(db_path: Path) -> dict:
    """Independent SQL directly on released tables, not FictionStore methods."""
    with closing(sqlite3.connect(db_path.as_uri() + "?mode=ro", uri=True)) as conn:
        conn.row_factory = sqlite3.Row
        top = conn.execute("""
            SELECT oi.product_id, SUM(oi.quantity) units
            FROM order_items oi JOIN orders o ON o.order_id=oi.order_id
            WHERE o.order_status='delivered' AND o.order_date>='2026-10-01'
              AND o.order_date<'2026-11-01'
            GROUP BY oi.product_id ORDER BY units DESC, oi.product_id LIMIT 3
        """).fetchall()
        missing = conn.execute("""SELECT c.case_id FROM fulfillment_cases c
            WHERE NOT EXISTS (SELECT 1 FROM inventory_snapshots_v2 s WHERE s.case_id=c.case_id)
            ORDER BY c.case_id""").fetchall()
        anomalous = conn.execute("""SELECT r.return_id FROM returns r JOIN orders o ON o.order_id=r.order_id
            WHERE r.refund_amount > o.total_amount ORDER BY r.return_id LIMIT 1""").fetchone()
        return {"top3": [dict(x) for x in top], "cases_without_snapshot": [x[0] for x in missing],
                "refund_above_order": anomalous[0] if anomalous else None}


def audit(db_path: Path, manifest_path: Path) -> dict:
    verified = verify_release(db_path, manifest_path)
    source = FictionStore(db_path, verified)
    expected = _oracle(db_path)
    ranked = source.top_sellers("2026-10", 3)
    assert [(r['product_id'], r['delivered_units']) for r in ranked['data']] == [
        (r['product_id'], r['units']) for r in expected['top3']]
    assert "PARTIAL_OR_FUTURE_PERIOD" not in ' '.join(ranked['limitations'])
    assert "PARTIAL_OR_FUTURE_PERIOD" in ' '.join(source.top_sellers("2026-11")['limitations'])
    missing = expected['cases_without_snapshot']
    assert missing
    case = source.fulfillment_case(missing[0])
    assert case['data']['snapshots'] == [] and case['data']['evidence_candidates'] == []
    assert "NO_CASE_SNAPSHOT" in case['limitations']
    returned = source.refund(expected['refund_above_order'])
    assert returned['data']['refund_above_order_value'] is True
    assert returned['data']['product_id'] == returned['scope']['product_id']
    sku = ranked['data'][0]['sku']
    stock = source.inventory(sku)
    assert stock['scope']['product_id'] == ranked['data'][0]['product_id']
    assert all(r['available_snapshot'] == r['quantity_on_hand']-r['reserved_quantity'] for r in stock['data'])
    assert all('customer_id' not in str(v) and 'email' not in str(v) for v in (stock, returned, case))
    return {"status":"PASS", "mode":"read_only_local_fiction_sql", "release":verified,
            "oracle":{"top3":expected['top3'],"missing_case_count":len(missing),
                      "example_missing_case":missing[0],"example_refund_anomaly":expected['refund_above_order']},
            "checks":["release_integrity", "sku_identity", "top_seller_sql", "partial_month",
                      "case_missing_snapshot", "refund_anomaly", "inventory_same_product", "no_customer_pii"]}


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument('--db',type=Path,default=Path('data/fiction/fiction_retail.sqlite'))
    p.add_argument('--manifest',type=Path,default=Path('data/fiction/manifest.json'))
    p.add_argument('--output',type=Path,default=None)
    a=p.parse_args()
    result = audit(a.db.resolve(), a.manifest.resolve())
    text=json.dumps(result,indent=2,ensure_ascii=False)
    if a.output:
        a.output.parent.mkdir(parents=True,exist_ok=True)
        a.output.write_text(text+'\n',encoding='utf-8')
    print(text)

if __name__ == '__main__':
    main()
