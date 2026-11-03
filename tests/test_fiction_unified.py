"""Small scenario tests for Fiction SQL read boundaries (independent of real DB)."""
from __future__ import annotations
from hashlib import sha256
import sqlite3
from pathlib import Path
from uuid import UUID

import pytest
from retailiq.domain.fiction import FictionStore, FictionDataError, _period, verify_release
from retailiq.infrastructure.sqlite import query

P1 = '11111111-1111-4111-8111-111111111111'
P2 = '22222222-2222-4222-8222-222222222222'
O1 = '33333333-3333-4333-8333-333333333333'
R1 = '44444444-4444-4444-8444-444444444444'
W1 = '55555555-5555-4555-8555-555555555555'
I1 = '66666666-6666-4666-8666-666666666666'
C1 = 'CASE-77777777-7777-4777-8777-777777777777'


@pytest.fixture
def fiction(tmp_path):
    p = tmp_path / 'fiction.sqlite'
    with sqlite3.connect(p) as c:
        c.executescript('''
        CREATE TABLE products(product_id TEXT, sku TEXT, name TEXT, category TEXT, brand TEXT, price REAL);
        CREATE TABLE orders(order_id TEXT, customer_id TEXT, order_date TEXT, order_status TEXT, total_amount REAL);
        CREATE TABLE order_items(order_item_id TEXT, order_id TEXT, product_id TEXT, quantity INT, unit_price REAL, discount_pct INT);
        CREATE TABLE shipments(shipment_id TEXT, order_id TEXT, warehouse_id TEXT, shipped_date TEXT, delivered_date TEXT, shipment_state TEXT);
        CREATE TABLE inventory(inventory_id TEXT, product_id TEXT, warehouse_id TEXT, quantity_on_hand INT, reserved_quantity INT, last_restocked_date TEXT);
        CREATE TABLE returns(return_id TEXT, order_id TEXT, product_id TEXT, return_date TEXT, refund_amount REAL, return_reason_code TEXT);
        CREATE TABLE fulfillment_cases(case_id TEXT, order_id TEXT, order_item_id TEXT, product_id TEXT, request_qty INT, assigned_warehouse_id TEXT, case_date TEXT);
        CREATE TABLE operational_events(event_id TEXT, case_id TEXT, event_type TEXT, occurred_at TEXT, recorded_at TEXT);
        CREATE TABLE inventory_snapshots_v2(snapshot_id TEXT, case_id TEXT, product_id TEXT, warehouse_id TEXT, observed_at TEXT, received_at TEXT, on_hand INT, reserved INT);
        CREATE TABLE warehouse_eligibility(case_id TEXT, warehouse_id TEXT, eligible INT, reason_code TEXT);
        ''')
        sku=lambda pid: 'FR-'+sha256(pid.encode()).hexdigest()[:16].upper()
        c.executemany('INSERT INTO products VALUES(?,?,?,?,?,?)',[(P1,sku(P1),'Device','electronics','Brand',20.0),
                                                                   (P2,sku(P2),'Other','electronics','Brand',25.0)])
        c.execute('INSERT INTO orders VALUES (?,?,?,?,?)',(O1,'CUSTOMER_SECRET','2026-10-15','delivered',20.0))
        c.execute('INSERT INTO order_items VALUES(?,?,?,?,?,?)',(I1,O1,P1,2,10.0,0))
        c.execute('INSERT INTO inventory VALUES (?,?,?,?,?,?)',(I1,P1,W1,4,1,'2026-10-01'))
        c.execute('INSERT INTO returns VALUES (?,?,?,?,?,?)',(R1,O1,P1,'2026-10-18',30.0,'DAMAGED'))
        c.execute('INSERT INTO fulfillment_cases VALUES(?,?,?,?,?,?,?)',(C1,O1,I1,P1,2,W1,'2026-10-16'))
        c.execute('INSERT INTO operational_events VALUES(?,?,?,?,?)',('event1',C1,'evidence_cutoff_reached','2026-10-16T12:00:00Z','2026-10-16T12:01:00Z'))
        c.execute('INSERT INTO warehouse_eligibility VALUES(?,?,?,?)',(C1,W1,1,'ALLOWED'))
    info={'pack_version':'fiction-retail-unified-v1.0.0', 'runtime_sha256':'fixture-only',
          'dataset_business_as_of':'2026-11-03T00:00:00+07:00'}
    return p,FictionStore(p,info)


def test_scoped_identity_and_nonpii(fiction):
    p,s=fiction
    sku='FR-'+sha256(P1.encode()).hexdigest()[:16].upper()
    assert s.resolve_product(sku)==P1
    assert s.product(sku)['data']['product_id']==P1
    assert s.resolve_product(P2)==P2
    assert s.inventory(P1)['data'][0]['available_snapshot']==3
    assert 'UNDATED_INVENTORY' in s.inventory(P1)['limitations'][0]
    assert s.inventory(P2)['data']==[]
    assert 'NO_INVENTORY_RECORDS' in s.inventory(P2)['limitations'][1]
    assert 'CUSTOMER_SECRET' not in str(s.order(O1))
    assert all(i['product_id']==P1 for i in s.top_sellers('2026-10')['data'])
    assert s.top_sellers('2026-10')['data'][0]['delivered_units']==2
    assert 'PARTIAL_OR_FUTURE_PERIOD' in ' '.join(s.top_sellers('2026-11')['limitations'])


def test_refund_anomaly_not_payment(fiction):
    _,s=fiction
    r=s.refund(R1)
    assert r['data']['refund_above_order_value'] is True
    assert r['data']['refund_above_returned_product_lines'] is True
    assert r['data']['returned_product_lines_net_usd']=='20.00'
    assert 'not evidence of approved' in r['limitations'][0]


def test_case_missing_and_stale_snapshot(fiction):
    p,s=fiction
    case=s.fulfillment_case(C1)
    assert case['data']['evidence_candidates']==[]
    assert case['limitations'][0]=='NO_CASE_SNAPSHOT'
    with sqlite3.connect(p) as db:
        db.execute('INSERT INTO inventory_snapshots_v2 VALUES(?,?,?,?,?,?,?,?)',
                   ('snap1',C1,P1,W1,'2026-10-15T10:00:00Z','2026-10-15T10:05:00Z',10,0))
    assert s.fulfillment_case(C1)['data']['evidence_candidates']==[]  # > 24h before cutoff
    with sqlite3.connect(p) as db:
        db.execute('INSERT INTO inventory_snapshots_v2 VALUES(?,?,?,?,?,?,?,?)',
                   ('snap2',C1,P1,W1,'2026-10-16T11:00:00Z','2026-10-16T11:05:00Z',5,1))
    good=s.fulfillment_case(C1)
    assert len(good['data']['evidence_candidates'])==1
    assert 'approval' in good['limitations'][-1]
    with sqlite3.connect(p) as db:
        db.execute('INSERT INTO inventory_snapshots_v2 VALUES(?,?,?,?,?,?,?,?)',
                   ('snap3',C1,P1,W1,'2026-10-16T11:30:00Z','2026-10-16T11:35:00Z',0,0))
    assert s.fulfillment_case(C1)['data']['evidence_candidates']==[]  # latest observation supersedes older candidate


def test_fail_closed_validation_and_readonly(fiction, tmp_path):
    p,s=fiction
    with pytest.raises(ValueError): s.resolve_product('EL-001')
    with pytest.raises(ValueError): s.order('NOT-AN-ORDER')
    with pytest.raises(ValueError): s.top_sellers('2026-13')
    with pytest.raises(ValueError): s.top_sellers('2026-10',0)
    with pytest.raises(ValueError): query('DELETE FROM products',db_path=p)
    with pytest.raises(sqlite3.OperationalError): query('SELECT * FROM non_existing_table',db_path=p)
    with pytest.raises(FictionDataError): verify_release(p,tmp_path/'not_present_manifest.json')


def test_period_bounds():
    assert _period('2026-12')==('2026-12-01','2027-01-01')
