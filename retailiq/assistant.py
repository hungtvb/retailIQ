from .analytics import products,inventory,revenue,top,month,requested_month
from .retrieval import retrieve
from .observability import log_event, observed
import os
# Load project .env at application import, before RETAILIQ_MODE is first checked.
from .core import config as _provider_config

def intent(q):
 q=q.lower()
 if any(x in q for x in ['top seller','best seller','bán chạy']):return 'top'
 if any(x in q for x in ['revenue','doanh thu','sales performance']):return 'revenue'
 if any(x in q for x in ['stock','inventory','tồn kho','in stock','available units','còn hàng','còn bao nhiêu']):return 'stock'
 if any(x in q for x in ['product','sản phẩm','spec','specification','warranty','bảo hành','charger','laptop','usb-c','alphabook','guide','manual','policy','chính sách']):return 'product'
 if product_sku(q):return 'product'
 return 'general'
def product_sku(q):
 """Recognize only a unique full product name or an explicit SKU."""
 import re
 text=q.casefold()
 matches={p['sku'] for p in products()
          if re.search(r'(?<![\w-])'+re.escape(p['sku'].casefold())+r'(?![\w-])',text)
          or re.search(r'(?<!\w)'+re.escape(p['name'].casefold())+r'(?!\w)',text)}
 return next(iter(matches)) if len(matches)==1 else None

def wants_single_top_product(q: str) -> bool:
 import re
 text=q.casefold()
 if re.search(r'\b(top\s*[2-9]|top\s*10|top\s+five|top\s+products|best sellers|top sellers)\b',text):
  return False
 return bool(re.search(r'bán chạy nhất|bán chạy số 1|sản phẩm bán chạy nhất|best seller\b|top\s*1\b|number one seller|#1 seller',text))

def wants_single_latest_product(q: str) -> bool:
 import re
 text=q.casefold()
 if re.search(r'\b(top\s*[2-9]|top\s*10|latest products|newest products|new products)\b',text):
  return False
 return 'mới nhất' in text or bool(re.search(r'\b(latest product|newest product|top\s*1)\b',text))
def do(q,category):
 if category=='latest':
  from .domain.analytics import newest_products
  from .orchestration.week1_graph import retailiq_reply
  rows=newest_products(1 if wants_single_latest_product(q) else 5)
  answer=retailiq_reply({'question':q,'intent':'latest','records':rows,'answer':''})['answer']
  return {'answer':answer,'records':rows,'contexts':[]}
 if category=='general':
  from .language import is_vietnamese
  answer=('Xin chào! Tôi là RetailIQ. Bạn có thể hỏi về tồn kho, doanh thu, hàng bán chạy hoặc thông tin sản phẩm.'
          if is_vietnamese(q) else
          'Hello! I am RetailIQ. You can ask about inventory, revenue, top sellers, or product information.')
  return {'answer':answer,'records':[],'contexts':[]}
 if category=='stock':
  sku=product_sku(q)
  if not sku:return {'answer':'Please specify a known product name or SKU.','records':[],'contexts':[]}
  rows=inventory(sku)
  if not rows:
   return {'answer':f'No inventory records are available for SKU {sku}.', 'records':[], 'contexts':[]}
  total=sum(r['available'] for r in rows)
  return {'answer':f"{rows[0]['name']} ({sku}): {total} available units across locations. "+'; '.join(f"{r['location']}: {r['available']} available (on hand {r['on_hand']}, reserved {r['reserved']})" for r in rows)+'.','records':rows,'contexts':[]}
 if category=='revenue':
  period=requested_month(q)
  rows=revenue(period) if period!=month() else revenue()
  if not rows:
   return {'answer':f'No completed-order sales records for {period}.', 'records':[], 'contexts':[], 'period':period}
  total=sum(r['net_revenue_vnd'] for r in rows)
  return {'answer':f'Net sales revenue in {period}: {total:,} VND (completed orders, after line discounts, before returns). '+'; '.join(f"{r['channel']}: {r['net_revenue_vnd']:,} VND" for r in rows)+'.','records':rows,'contexts':[], 'period':period}
 if category=='top':
  period=requested_month(q)
  ranked=top(period) if period!=month() else top()
  rows=ranked[:1] if wants_single_top_product(q) else ranked
  if not rows:
   return {'answer':f'No completed-order top sellers for {period}.','records':[],'contexts':[], 'period':period}
  return {'answer':f'Top sellers by units in {period} (completed orders): '+ '; '.join(f"{i+1}. {r['name']} ({r['sku']}): {r['units_sold']} units" for i,r in enumerate(rows))+'.','records':rows,'contexts':[], 'period':period}
 if category=='product' and any(word in q.casefold() for word in ('giá','price','cost')) and product_sku(q):
  from .domain.analytics import catalog_product
  from .orchestration.week1_graph import retailiq_reply
  item=catalog_product(product_sku(q))
  rows=[item] if item else []
  answer=retailiq_reply({'question':q,'intent':'product','records':rows,'answer':''})['answer'] if rows else 'No matching catalog product.'
  return {'answer':answer,'records':rows,'contexts':[]}
 docs=retrieve(q)
 return {'answer':f"Source: {docs[0]['source']}\n{docs[0]['text']}" if docs else 'No matching product documentation.','records':[],'contexts':docs}
def offline(q, *, history=None, active_agent=''):
 from .orchestration.week1_graph import followup_intent, resolve_followup, AGENT_FOR_INTENT
 from .orchestration.agents import replenish_review
 from .skills import skill_for
 category=followup_intent(q,history)
 effective=resolve_followup(q,history,category)
 agent=AGENT_FOR_INTENT[category]
 log_event('agent.routed', intent=category, agent=agent, execution_mode='offline')
 log_event('skill.selected', skill=skill_for(category), execution_mode='offline')
 with observed('tool.offline_lookup', agent=agent, tool='reviewed_sql_or_lexical', execution_mode='offline'):
  result=replenish_review_offline() if category=='decision' else do(effective,category)
 agent=AGENT_FOR_INTENT[category]
 handoff=({'from':'sales_agent','to':'inventory_agent',
           'reason':'Follow-up inventory question'}
          if active_agent=='sales_agent' and category=='stock' else None)
 if handoff: log_event('agent.handoff', previous_agent='sales_agent', target_agent='inventory_agent', execution_mode='offline')
 return {'question':q,'intent':category,
         'mode':'OFFLINE deterministic fallback — not LangGraph/VectorDB',
         'as_of':result.get('period',month()),'active_agent':agent,'handoff':handoff,
         'subagents':['sales_agent','inventory_agent'] if category=='decision' else [],
         'skill':skill_for(category), **result}

def replenish_review_offline():
 # No LangGraph is claimed in offline mode. The same transparent policy is
 # exercised with local reviewed SQL for stakeholder demonstration.
 from .domain.analytics import top,inventory
 rows=top()
 if not rows:return {'answer':'No completed-order data','records':[],'contexts':[]}
 leader=rows[0]
 stocks=inventory(leader['sku'])
 if not stocks:
  return {'answer':f"Cannot assess replenishment for {leader['sku']}: inventory evidence is missing. No purchasing recommendation is made.",'records':rows[:1],'contexts':[]}
 available=sum(x['available'] for x in stocks)
 priority='REVIEW replenishment priority' if available<leader['units_sold'] else 'No immediate priority under this heuristic'
 return {'answer':f"Synthetic {month()} decision review: {leader['name']} sold {leader['units_sold']} units; {available} available. {priority}. Not a forecast or purchase order.",
         'records':[leader,*stocks],'contexts':[]}

def ask(q, *, history=None, active_agent=''):
 if os.getenv('RETAILIQ_MODE')=='full':
  from .graph import run
  if history or active_agent:
   return run(q,history=history or [],active_agent=active_agent)
  return run(q)
 return offline(q,history=history,active_agent=active_agent)

