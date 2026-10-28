import pytest
from retailiq.analytics import inventory,revenue,top,products,month
from retailiq.assistant import offline
from retailiq.db import query

def test_data():assert len(products())==10
def test_stock():
 rows=inventory('EL-001');assert len(rows)==3
 assert all(r['available']==r['on_hand']-r['reserved']>=0 for r in rows)
def test_revenue():
 expected=query("SELECT SUM(li.quantity*li.unit_price_vnd-li.discount_vnd) n FROM orders o JOIN order_lines li ON li.order_id=o.id WHERE o.status='completed' AND substr(o.ordered_at,1,7)=?",(month(),))[0]['n']
 assert sum(r['net_revenue_vnd'] for r in revenue())==expected
def test_top():
 rows=top();assert len(rows)==5
 assert [r['units_sold'] for r in rows]==sorted((r['units_sold'] for r in rows),reverse=True)
def test_queries():
 for text,it in [('How many units of AlphaBook Pro 14 are in stock?','stock'),('What is the revenue this month?','revenue'),('Which products are top sellers?','top'),('Tell me about USB-C GaN Charger 65W','product')]:
  out=offline(text);assert out['intent']==it and out['answer']
def test_sql_guard():
 with pytest.raises(ValueError):query('DROP TABLE products')
