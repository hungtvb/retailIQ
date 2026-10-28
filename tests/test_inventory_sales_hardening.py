"""Inventory/Sales module acceptance: real SQLite fixtures and domain failure modes."""
from contextlib import closing
import sqlite3

import pytest

from retailiq.domain import analytics
from retailiq.infrastructure import sqlite as adapter
from retailiq import assistant


@pytest.fixture
def db(tmp_path, monkeypatch):
    path = tmp_path / 'domain.sqlite3'
    with closing(sqlite3.connect(path)) as conn, conn:
        conn.executescript('''
            CREATE TABLE products(sku TEXT PRIMARY KEY, name TEXT, category TEXT);
            CREATE TABLE locations(id TEXT PRIMARY KEY, name TEXT, channel TEXT);
            CREATE TABLE inventory(sku TEXT, location_id TEXT, on_hand, reserved, updated_at);
            CREATE TABLE orders(id TEXT PRIMARY KEY, ordered_at TEXT, channel TEXT, status TEXT);
            CREATE TABLE order_lines(id INTEGER PRIMARY KEY, order_id TEXT, sku TEXT,
                quantity, unit_price_vnd, discount_vnd);
        ''')
        conn.executemany('INSERT INTO products VALUES (?,?,?)', [
            ('SKU-1', 'Blue Laptop', 'Electronics'),
            ('SKU-2', 'Red Laptop', 'Electronics'),
            ('SKU-3', 'Inactive Product', 'Electronics'),
        ])
        conn.executemany('INSERT INTO locations VALUES (?,?,?)', [
            ('L1', 'Warehouse', 'warehouse'), ('L2', 'Store', 'store'),
        ])
        conn.executemany('INSERT INTO inventory VALUES (?,?,?,?,?)', [
            ('SKU-1', 'L1', 15, 4, '2026-10-28 09:00 +07:00'),
            ('SKU-1', 'L2', 3, 3, '2026-10-27T10:00:00+07:00'),
            ('SKU-2', 'L1', 5, 0, '2026-10-25 09:00 +07:00'),
        ])
        conn.executemany('INSERT INTO orders VALUES (?,?,?,?)', [
            ('O1','2026-10-01','online','completed'),
            ('O2','2026-10-31T23:59:59+07:00','store','completed'),
            ('O3','2026-10-13','online','cancelled'),
            ('O4','2026-09-30T23:59:59+07:00','online','completed'),
            ('O5','2026-11-01','online','completed'),
        ])
        conn.executemany('INSERT INTO order_lines VALUES (?,?,?,?,?,?)', [
            (1,'O1','SKU-1',2,100_000,20_000),
            (2,'O2','SKU-2',2,150_000,0),
            (3,'O3','SKU-1',80,100_000,0),
            (4,'O4','SKU-1',90,100_000,0),
            (5,'O5','SKU-1',90,100_000,0),
        ])
    monkeypatch.setenv('RETAILIQ_AS_OF','2026-10-28')
    monkeypatch.setattr(adapter, 'DB', path)
    return path


def modify(db, sql, params=()):
    with closing(sqlite3.connect(db)) as conn, conn:
        conn.execute(sql, params)


def test_inventory_exact_availability_and_normalized_sku(db):
    rows = analytics.inventory(' sku-1 ')
    assert [r['location_id'] for r in rows] == ['L1', 'L2']
    assert [(r['on_hand'],r['reserved'],r['available']) for r in rows] == [(15,4,11),(3,3,0)]
    assert sum(r['available'] for r in rows) == 11


def test_known_product_missing_inventory_never_crashes_or_invents_zero(db, monkeypatch):
    assert analytics.inventory('SKU-3') == []
    monkeypatch.setattr(assistant, 'products', analytics.products)
    monkeypatch.setattr(assistant, 'inventory', analytics.inventory)
    reply = assistant.do('How much stock for SKU-3?', 'stock')
    assert not reply['records']
    assert 'no inventory' in reply['answer'].lower()


@pytest.mark.parametrize('sku', [None, '', ' ', 'SKU-1; DROP TABLE products', 'A'*65, 123])
def test_invalid_skus_rejected(db, sku):
    with pytest.raises(ValueError):
        analytics.inventory(sku)


@pytest.mark.parametrize('field,value', [
    ('reserved',-1),('on_hand',-1),('reserved',99),('on_hand',None),
    ('reserved','unavailable'),('updated_at','garbage'),('updated_at','2026-10-28'),
])
def test_corrupt_inventory_rejected_not_summed(db, field, value):
    modify(db, f'UPDATE inventory SET {field}=? WHERE sku=? AND location_id=?',
           (value, 'SKU-1', 'L1'))
    with pytest.raises(analytics.DomainDataError):
        analytics.inventory('SKU-1')


def test_duplicate_and_orphan_location_rejected(db):
    modify(db, 'INSERT INTO inventory VALUES (?,?,?,?,?)',
           ('SKU-1','L1',2,0,'2026-10-28 09:00 +07:00'))
    with pytest.raises(analytics.DomainDataError, match='duplicate'):
        analytics.inventory('SKU-1')
    modify(db, "DELETE FROM inventory WHERE sku='SKU-1' AND on_hand=2")
    modify(db, "UPDATE inventory SET location_id='MISSING' WHERE sku='SKU-1' AND location_id='L1'")
    with pytest.raises(analytics.DomainDataError, match='location'):
        analytics.inventory('SKU-1')


def test_temporary_sql_failure_not_silenced_as_zero_stock(db, monkeypatch):
    def broken(*_a, **_kw):
        raise sqlite3.OperationalError('database is locked')
    monkeypatch.setattr(analytics, 'query', broken)
    with pytest.raises(sqlite3.OperationalError):
        analytics.inventory('SKU-1')


def test_sales_completed_orders_discount_date_boundaries_and_ties(db):
    assert analytics.revenue() == [
        {'channel':'online','orders':1,'net_revenue_vnd':180_000},
        {'channel':'store','orders':1,'net_revenue_vnd':300_000},
    ]
    assert [(r['sku'],r['units_sold']) for r in analytics.top()] == [
        ('SKU-1',2), ('SKU-2',2),
    ]


def test_month_bounds_and_empty_period(db, monkeypatch):
    monkeypatch.setenv('RETAILIQ_AS_OF','2026-12-15')
    assert analytics._month_bounds() == ('2026-12-01','2027-01-01')
    assert analytics.revenue() == []
    assert analytics.top() == []


def test_invalid_configured_date_fails_closed(db, monkeypatch):
    monkeypatch.setenv('RETAILIQ_AS_OF','2026-02-30')
    with pytest.raises(ValueError):
        analytics.revenue()


def test_no_completed_orders_empty_reports(db):
    modify(db, "UPDATE orders SET status='cancelled'")
    assert analytics.revenue() == []
    assert analytics.top() == []


@pytest.mark.parametrize('column,value', [
    ('quantity',0),('quantity',-1),('quantity','two'),('quantity',None),
    ('unit_price_vnd',-1),('unit_price_vnd','oops'),('unit_price_vnd',None),
    ('discount_vnd',-1),('discount_vnd',200_001),('discount_vnd','oops'),('discount_vnd',None),
])
def test_bad_completed_order_lines_rejected_in_both_reports(db, column, value):
    modify(db, f'UPDATE order_lines SET {column}=? WHERE id=1', (value,))
    with pytest.raises(analytics.DomainDataError, match='completed-order line'):
        analytics.revenue()
    with pytest.raises(analytics.DomainDataError, match='completed-order line'):
        analytics.top()


def test_cancelled_order_corruption_does_not_affect_kpi(db):
    modify(db, "UPDATE order_lines SET quantity='bad' WHERE id=3")
    assert sum(r['net_revenue_vnd'] for r in analytics.revenue()) == 480_000


def test_unknown_product_reference_rejected(db):
    modify(db, "UPDATE order_lines SET sku='INVALID' WHERE id=1")
    with pytest.raises(analytics.DomainDataError):
        analytics.revenue()
    with pytest.raises(analytics.DomainDataError):
        analytics.top()


def test_missing_sales_channel_rejected(db):
    modify(db, 'UPDATE orders SET channel=NULL WHERE id=?', ('O1',))
    with pytest.raises(analytics.DomainDataError, match='channel'):
        analytics.revenue()


def test_business_data_error_not_automatically_retried():
    from retailiq.orchestration.week1_graph import retryable_read_failure
    assert not retryable_read_failure(analytics.DomainDataError('bad stock'))


def test_no_sales_data_explained_without_fake_ranking(db):
    modify(db, "UPDATE orders SET status='cancelled'")
    assert 'No completed-order' in assistant.do('What is revenue?', 'revenue')['answer']
    assert 'No completed-order' in assistant.do('Which are top sellers?', 'top')['answer']


def test_replenishment_not_assessed_without_stock_evidence(db):
    modify(db, "DELETE FROM inventory WHERE sku='SKU-1'")
    from retailiq import assistant as a
    # The top-ranked seller is SKU-1 under deterministic tie ordering.
    result = a.replenish_review_offline()
    assert 'inventory evidence is missing' in result['answer']
    assert 'No purchasing recommendation' in result['answer']
    assert len(result['records']) == 1
