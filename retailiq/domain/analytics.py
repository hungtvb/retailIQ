import os
from datetime import date
from retailiq.infrastructure.sqlite import query
def month():return date.fromisoformat(os.getenv('RETAILIQ_AS_OF','2026-10-28')).strftime('%Y-%m')
def products():return query('SELECT * FROM products ORDER BY sku')
def inventory(sku):return query('''SELECT p.sku,p.name,l.name AS location,l.channel,i.on_hand,i.reserved,(i.on_hand-i.reserved) available,i.updated_at FROM inventory i JOIN products p ON p.sku=i.sku JOIN locations l ON l.id=i.location_id WHERE p.sku=? ORDER BY l.id''',(sku,))
def revenue():return query('''SELECT o.channel,COUNT(DISTINCT o.id) orders,SUM(li.quantity*li.unit_price_vnd-li.discount_vnd) net_revenue_vnd FROM orders o JOIN order_lines li ON li.order_id=o.id WHERE o.status='completed' AND substr(o.ordered_at,1,7)=? GROUP BY o.channel ORDER BY o.channel''',(month(),))
def top():return query('''SELECT p.sku,p.name,SUM(li.quantity) units_sold FROM orders o JOIN order_lines li ON li.order_id=o.id JOIN products p ON p.sku=li.sku WHERE o.status='completed' AND substr(o.ordered_at,1,7)=? GROUP BY p.sku,p.name ORDER BY units_sold DESC,p.sku LIMIT 5''',(month(),))
