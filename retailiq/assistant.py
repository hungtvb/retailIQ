"""Public assistant entrypoint; shared lookup logic lives in queries.py."""
from .analytics import month
from .queries import intent, product_sku, wants_single_top_product, wants_single_latest_product, do
from .observability import log_event, observed
import os
# Load project .env at application import, before RETAILIQ_MODE is first checked.
from .core import config as _provider_config

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

