from .analytics import products,inventory,revenue,top,month
from .retrieval import retrieve
from .observability import log_event, observed
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
def offline(q, *, history=None, active_agent=''):
 from .orchestration.week1_graph import classify, resolve_followup, AGENT_FOR_INTENT
 from .orchestration.agents import replenish_review
 from .skills import skill_for
 category=classify(q)
 effective=resolve_followup(q,history)
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
         'as_of':month(),'active_agent':agent,'handoff':handoff,
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

