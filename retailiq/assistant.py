from .analytics import products,inventory,revenue,top,month
from .retrieval import retrieve
import os
# Load project .env at application import, before RETAILIQ_MODE is first checked.
from .core import config as _provider_config

def intent(q):
 q=q.lower()
 if any(x in q for x in ['top seller','best seller','bán chạy']):return 'top'
 if any(x in q for x in ['revenue','doanh thu','sales performance']):return 'revenue'
 if any(x in q for x in ['stock','inventory','tồn kho','in stock','available units']):return 'stock'
 return 'product'
def product_sku(q):
 q=q.lower()
 for p in products():
  if p['name'].lower() in q or p['sku'].lower() in q or p['name'].lower().split()[0] in q:return p['sku']
 return None
def do(q,category):
 if category=='stock':
  sku=product_sku(q)
  if not sku:return {'answer':'Please specify a known product name or SKU.','records':[],'contexts':[]}
  rows=inventory(sku)
  total=sum(r['available'] for r in rows)
  return {'answer':f"{rows[0]['name']} ({sku}): {total} available units across locations. "+'; '.join(f"{r['location']}: {r['available']} available (on hand {r['on_hand']}, reserved {r['reserved']})" for r in rows)+'.','records':rows,'contexts':[]}
 if category=='revenue':
  rows=revenue(); total=sum(r['net_revenue_vnd'] for r in rows)
  return {'answer':f'Net sales revenue in {month()}: {total:,} VND (completed orders, after line discounts, before returns). '+'; '.join(f"{r['channel']}: {r['net_revenue_vnd']:,} VND" for r in rows)+'.','records':rows,'contexts':[]}
 if category=='top':
  rows=top();return {'answer':f'Top sellers by units in {month()} (completed orders): '+ '; '.join(f"{i+1}. {r['name']} ({r['sku']}): {r['units_sold']} units" for i,r in enumerate(rows))+'.','records':rows,'contexts':[]}
 docs=retrieve(q)
 return {'answer':f"Source: {docs[0]['source']}\n{docs[0]['text']}" if docs else 'No matching product documentation.','records':[],'contexts':docs}
def offline(q):
 cat=intent(q)
 return {'question':q,'intent':cat,'mode':'OFFLINE deterministic fallback — not LangGraph/VectorDB', 'as_of':month(),**do(q,cat)}
def ask(q):
 if os.getenv('RETAILIQ_MODE')=='full':
  from .graph import run
  return run(q)
 return offline(q)
