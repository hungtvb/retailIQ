"""Fiction source contracts: scoped queries, corruption, and source-linked RAG."""
from __future__ import annotations

import json
from pathlib import Path
import os
import sqlite3

import pytest

from retailiq.domain import fiction
from scripts.build_fiction_rag import generate

A = '00000000-0000-4000-8000-000000000001'
B = '00000000-0000-4000-8000-000000000002'


def fixture(path: Path):
    with sqlite3.connect(path) as c:
        c.executescript("""
            CREATE TABLE products(product_id TEXT,name TEXT,category TEXT,brand TEXT,price REAL,weight_kg REAL);
            CREATE TABLE warehouses(warehouse_id TEXT,name TEXT);
            CREATE TABLE inventory(product_id TEXT,warehouse_id TEXT,quantity_on_hand INTEGER,reserved_quantity INTEGER,reorder_threshold INTEGER,last_restocked_date TEXT);
            CREATE TABLE orders(order_id TEXT,customer_id TEXT,order_date TEXT,order_status TEXT);
            CREATE TABLE order_items(order_item_id TEXT,order_id TEXT,product_id TEXT,quantity INTEGER,unit_price REAL,discount_pct REAL);
            CREATE TABLE returns(return_id TEXT,order_id TEXT,return_date TEXT,product_id TEXT,return_reason_code TEXT);
        """)
        c.executemany('INSERT INTO products VALUES (?,?,?,?,?,?)', [(A,'A','electronics','X',10,0.1),(B,'B','electronics','Y',20,0.2)])
        c.execute("INSERT INTO warehouses VALUES ('W1','Main')")
        c.executemany('INSERT INTO inventory VALUES (?,?,?,?,?,?)', [(A,'W1',12,4,8,'2024-03-01'),(B,'W1',1,0,0,'2024-03-01')])
        c.executemany('INSERT INTO orders VALUES (?,?,?,?)', [('O1','SECRET-CUSTOMER','2024-04-10','returned'),('O2','SECRET-CUSTOMER','2024-04-11','delivered'),('O3','SECRET-CUSTOMER','2024-05-10','delivered')])
        c.executemany('INSERT INTO order_items VALUES (?,?,?,?,?,?)', [('I1','O1',A,3,10,10),('I2','O2',B,1,20,0),('I3','O3',B,9,20,0)])
        c.execute("INSERT INTO returns VALUES ('R1','O1','2024-04-12',?,'DEFECTIVE')",(A,))


def test_scope_and_read_only(tmp_path):
    source=tmp_path/'f.db'; fixture(source)
    assert fiction.product(source,A)['name']=='A'
    stock=fiction.stock(source,A)
    assert stock[0]['available']==8
    assert stock[0]['below_reorder_threshold'] is True
    assert stock[0]['freshness']=='UNVERIFIED_HISTORICAL_SNAPSHOT'
    assert fiction.top_sellers(source,'2024-04')[0]['product_id']==B
    assert fiction.delivered_merchandise_value(source,'2024-04')['amount_usd']=='20.00'
    assert fiction.delivered_merchandise_value(source,'2024-05')['amount_usd']=='180.00'
    assert fiction.return_reasons(source,'2024-04',product_id=A)==[{'reason_code':'DEFECTIVE','return_events':1}]
    with fiction.connect(source) as db:
        with pytest.raises(sqlite3.OperationalError):
            db.execute('DELETE FROM orders')
    with pytest.raises(ValueError):
        fiction.product(source,'EL-001')
    with pytest.raises(ValueError):
        fiction.top_sellers(source,'2024-13')
    with pytest.raises(ValueError):
        fiction.top_sellers(source,'2024-04',limit=0)


def test_corrupt_stock_and_discount_fail_closed(tmp_path):
    source=tmp_path/'f.db'; fixture(source)
    with sqlite3.connect(source) as db:
        db.execute('UPDATE inventory SET reserved_quantity=99 WHERE product_id=?',(A,))
        db.execute("UPDATE order_items SET discount_pct=150 WHERE order_item_id='I2'")
    with pytest.raises(fiction.FictionDataError):
        fiction.stock(source,A)
    with pytest.raises(fiction.FictionDataError):
        fiction.delivered_merchandise_value(source,'2024-04')


def test_generated_corpus_has_source_lineage_and_no_customer_identifier(tmp_path):
    source=tmp_path/'f.db'; fixture(source)
    out=tmp_path/'fiction_corpus'
    info=generate(source,out,max_products=2,max_reviews=2,max_tickets=1,category='electronics')
    assert info['counts']=={'products':2,'reviews':2,'support_tickets':1}
    assert info['metadata_records']==5
    rows=[json.loads(line) for line in (out/'records.jsonl').read_text().splitlines()]
    assert {r['product_id'] for r in rows} <= {A,B}
    assert all(r['is_synthetic_text'] for r in rows if r['kind']!='product_catalog')
    assert all(r.get('order_id') in ('O1','O2','O3') for r in rows if 'order_id' in r)
    assert any(r.get('return_id')=='R1' for r in rows)
    corpus='\n'.join(path.read_text() for path in out.rglob('*.md'))
    assert 'SECRET-CUSTOMER' not in corpus
    assert 'Synthetic Text: true' in corpus
    with pytest.raises(ValueError):
        generate(source,out,max_products=2)


def test_return_mismatch_rejected(tmp_path):
    source=tmp_path/'f.db'; fixture(source)
    with sqlite3.connect(source) as db:
        db.execute('UPDATE returns SET product_id=?',(B,))
    with pytest.raises(ValueError,match='lineage'):
        generate(source,tmp_path/'out',max_products=2)


@pytest.mark.skipif(not os.getenv('RETAILIQ_FICTION_DB'),reason='Provide local snapshot for source-backed acceptance')
def test_actual_fiction_snapshot():
    path=Path(os.environ['RETAILIQ_FICTION_DB'])
    with fiction.connect(path) as db:
        assert db.execute('SELECT COUNT(*) FROM products').fetchone()[0]==5000
        assert db.execute('SELECT COUNT(*) FROM orders').fetchone()[0]==150000
    assert fiction.delivered_merchandise_value(path,'2024-04')['amount_usd']=='18571791.10'
    assert len(fiction.top_sellers(path,'2024-04',limit=5))==5
