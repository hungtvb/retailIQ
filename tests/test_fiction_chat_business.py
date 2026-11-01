"""Business journey acceptance for Fiction, not agent/embedding evaluation."""
from __future__ import annotations
import os
from pathlib import Path
import sqlite3
import pytest

from retailiq import fiction_chat

P1 = '00000000-0000-4000-8000-000000000001'
P2 = '00000000-0000-4000-8000-000000000002'


def make_db(path):
    with sqlite3.connect(path) as db:
        db.executescript('''
        CREATE TABLE products(product_id TEXT,name TEXT,category TEXT,brand TEXT,price REAL,weight_kg REAL);
        CREATE TABLE warehouses(warehouse_id TEXT,name TEXT);
        CREATE TABLE inventory(product_id TEXT,warehouse_id TEXT,quantity_on_hand INT,reserved_quantity INT,reorder_threshold INT,last_restocked_date TEXT);
        CREATE TABLE orders(order_id TEXT,customer_id TEXT,order_date TEXT,order_status TEXT);
        CREATE TABLE order_items(order_item_id TEXT,order_id TEXT,product_id TEXT,quantity INT,unit_price REAL,discount_pct REAL);
        CREATE TABLE returns(return_id TEXT,order_id TEXT,product_id TEXT,return_date TEXT,return_reason_code TEXT);
        ''')
        db.executemany('INSERT INTO products VALUES (?,?,?,?,?,?)',[(P1,'First','apparel','X',13,1),(P2,'Second','books','Y',19,2)])
        db.executemany('INSERT INTO warehouses VALUES (?,?)',[('W1','Warehouse 1'),('W2','Warehouse 2')])
        db.executemany('INSERT INTO inventory VALUES (?,?,?,?,?,?)',[(P1,'W1',7,2,2,'2023-01-01'),(P1,'W2',3,1,2,'2023-01-01')])
        db.executemany('INSERT INTO orders VALUES (?,?,?,?)', [('O1','CUSTOMER_SECRET','2024-04-01','delivered'),('O2','CUSTOMER_SECRET','2024-04-30','returned'),('O3','CUSTOMER_SECRET','2024-03-01','delivered'),('O4','CUSTOMER_SECRET','2024-03-31','delivered')])
        db.executemany('INSERT INTO order_items VALUES (?,?,?,?,?,?)', [('I1','O1',P1,3,10,0),('I2','O2',P1,1,10,0),('I3','O3',P2,1,20,0),('I4','O4',P2,1,20,0)])
        db.execute('INSERT INTO returns VALUES (?,?,?,?,?)',('R1','O2',P1,'2024-04-30','DEFECTIVE'))

@pytest.fixture
def source(tmp_path, monkeypatch):
    path = tmp_path / 'fixture.db'; make_db(path)
    monkeypatch.setenv('RETAILIQ_FICTION_DB',str(path))
    monkeypatch.delenv('RETAILIQ_FICTION_CORPUS', raising=False)
    return path


def test_three_turn_business_trajectory(source):
    q1 = 'Top 2 sản phẩm bán chạy tháng 4/2024'
    a1 = fiction_chat.ask(q1)
    assert a1['data_status'] == 'OK' and a1['records'][0]['product_id'] == P1
    q2 = 'Sản phẩm số 1 còn bao nhiêu tồn kho?'
    a2 = fiction_chat.ask(q2, history=[{'role':'user','content':q1},{'role':'assistant','content':a1['answer']}])
    assert a2['selected_product_id'] == P1
    assert '7 đơn vị' in a2['answer']
    q3 = 'Có bị trả hàng và phàn nàn gì không?'
    a3 = fiction_chat.ask(q3, history=[{'role':'user','content':q1},{'role':'assistant','content':a1['answer']}, {'role':'user','content':q2},{'role':'assistant','content':a2['answer']}])
    assert a3['selected_product_id'] == P1
    assert 'DEFECTIVE' in a3['answer']
    assert 'Không có review khách hàng thực' in a3['answer']
    assert 'CUSTOMER_SECRET' not in repr(a3)


def test_ambiguous_refuses_guess(source):
    q = 'top 2 sản phẩm bán chạy tháng 4/2024'
    a = fiction_chat.ask('Có bị trả hàng không?',history=[{'role':'user','content':q}])
    assert a['data_status']=='CLARIFY' and a['selected_product_id'] is None
    a = fiction_chat.ask('Sản phẩm thứ 3 tồn kho?',history=[{'role':'user','content':q}])
    assert a['data_status']=='CLARIFY'


def test_future_period_not_zero_and_unknown_period(source):
    r=fiction_chat.ask('Doanh thu tháng 10/2026')
    assert r['data_status']=='DATA_NOT_AVAILABLE' and '0.00 USD' not in r['answer']
    assert fiction_chat.ask('Top 2 sản phẩm bán chạy')['data_status']=='CLARIFY'
    assert fiction_chat.ask('Doanh thu tháng 4/2024')['data_status']=='OK'


def test_compound_scopes_inventory_returns_and_abstains_on_reviews(source):
    r=fiction_chat.ask('Top 2 sản phẩm bán chạy tháng 4/2024 tồn kho, trả hàng, review')
    assert r['data_status']=='OK' and r['records'][0]['available_snapshot']==7
    assert r['records'][0]['return_events_by_return_date']==1
    assert 'Không thể suy ra tỷ lệ trả hàng' in r['answer']
    assert 'review khách hàng thực' not in r['answer'] or 'không phải feedback thật' in r['answer']
    assert r['mode']=='FICTION_DETERMINISTIC_SQL_NOT_LANGGRAPH'


@pytest.mark.skipif(not os.getenv('RETAILIQ_FICTION_DB'),reason='Real uploaded snapshot unavailable in CI')
def test_uploaded_fiction_real_world_journey(monkeypatch):
    source=Path(os.environ['RETAILIQ_FICTION_DB'])
    monkeypatch.setenv('RETAILIQ_FICTION_DB',str(source))
    first=fiction_chat.ask('Top 5 sản phẩm bán chạy tháng 4/2024')
    assert first['records'][0]['product_id']=='a7f98613-bf7f-41ce-bd40-0b4563a73edd'
    q='Sản phẩm số 1 còn bao nhiêu tồn kho?'
    stock=fiction_chat.ask(q,history=[{'role':'user','content':'Top 5 sản phẩm bán chạy tháng 4/2024'}])
    assert stock['selected_product_id']==first['records'][0]['product_id']
    assert sum(r['available'] for r in stock['records'] if 'available' in r)==6977
    ret=fiction_chat.ask('Có trả hàng và review gì không?',history=[{'role':'user','content':'Top 5 sản phẩm bán chạy tháng 4/2024'},{'role':'user','content':q}])
    assert ret['selected_product_id']==stock['selected_product_id']
    assert any('2 sự kiện trả hàng' in ret['answer'] for _ in [0])