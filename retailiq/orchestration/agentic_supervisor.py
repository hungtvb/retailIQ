"""Model-directed, read-only subagent delegation for a replenishment review.

The LangChain create_agent supervisor chooses which isolated domain tools to
call. Only verified SQL subgraph results enter the final business assessment.
"""
from __future__ import annotations
import json

from retailiq.core.config import chat_model
from retailiq.observability import log_event, observed
from retailiq.skills import load_skill
from retailiq.domain.analytics import products


def agentic_replenish_review(question: str) -> dict:
    from langchain.agents import create_agent
    from langchain.tools import tool
    from retailiq.orchestration.agents import build_sql_subagents, review_from_evidence

    sales_graph, inventory_graph = build_sql_subagents()
    outputs: dict[str, dict] = {}
    allowed = {p['sku'] for p in products()}

    @tool
    def sales_subagent(query: str) -> str:
        """Delegate a read-only completed-order ranking to the sales specialist."""
        with observed('agent.subagent', agent='retail_supervisor',
                      subagent='sales_agent', execution_mode='full'):
            result = sales_graph.invoke({'question': query, 'category': 'top'})['result']
        outputs['sales'] = result
        return json.dumps({'records': result['records'],
                           'instruction': load_skill('sales_kpi')}, ensure_ascii=False)

    @tool
    def inventory_subagent(sku: str) -> str:
        """Delegate an inventory lookup for an explicit product SKU."""
        if sku not in allowed:
            raise ValueError('Unknown SKU; use the SKU returned by sales_subagent')
        with observed('agent.subagent', agent='retail_supervisor',
                      subagent='inventory_agent', execution_mode='full'):
            result = inventory_graph.invoke({
                'question': f'How many units of {sku} are in stock?'
            })['result']
        outputs['inventory'] = result
        return json.dumps({'records': result['records'],
                           'instruction': load_skill('inventory_availability')},
                          ensure_ascii=False)

    agent = create_agent(
        model=chat_model(),
        tools=[sales_subagent, inventory_subagent],
        system_prompt=(load_skill('replenishment_review') + '\n'
                       'You coordinate two read-only specialists. For a '
                       'replenishment review, first call sales_subagent to '
                       'identify the top-selling SKU, then call '
                       'inventory_subagent using exactly that SKU. Never invent '
                       'data or create orders. Stop when evidence is complete.'),
    )
    # Explicit recursion bound prevents unbounded agent loops.
    agent.invoke({'messages': [{'role': 'user', 'content': question}]},
                 config={'recursion_limit': 10})
    if 'sales' not in outputs or 'inventory' not in outputs:
        log_event('agent.verification_failed', agent='retail_supervisor',
                  status='failed', error_type='IncompleteDelegation')
        raise ValueError('Supervisor did not collect verified sales and inventory evidence')
    result = review_from_evidence(outputs['sales'], outputs['inventory'])
    log_event('agent.supervisor_verified', agent='retail_supervisor',
              record_count=len(result['records']), execution_mode='full')
    return result
