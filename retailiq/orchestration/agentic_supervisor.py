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
        records = result.get('records')
        if not isinstance(records, list) or not records:
            raise ValueError('Sales specialist returned no top-seller evidence')
        leader = records[0]
        if not isinstance(leader, dict) or leader.get('sku') not in allowed:
            raise ValueError('Sales specialist returned an invalid top-selling SKU')
        outputs['sales'] = result
        return json.dumps({'records': records[:5],
                           'instruction': load_skill('sales_kpi')}, ensure_ascii=False)

    @tool
    def inventory_subagent(sku: str) -> str:
        """Delegate an inventory lookup for an explicit product SKU."""
        if 'sales' not in outputs:
            raise ValueError('Call sales_subagent before requesting inventory')
        top_sku = outputs['sales']['records'][0]['sku']
        if sku != top_sku or sku not in allowed:
            raise ValueError('Inventory SKU must match the verified top-selling SKU')
        if 'inventory' in outputs:
            raise ValueError('Inventory evidence has already been collected')
        with observed('agent.subagent', agent='retail_supervisor',
                      subagent='inventory_agent', execution_mode='full'):
            result = inventory_graph.invoke({
                'question': f'How many units of {sku} are in stock?'
            })['result']
        records = result.get('records')
        if not isinstance(records, list) or not records:
            raise ValueError('Inventory specialist returned no stock evidence')
        if any(not isinstance(row, dict) or row.get('sku') != sku for row in records):
            raise ValueError('Inventory specialist returned a mismatched SKU')
        outputs['inventory'] = result
        return json.dumps({'records': records[:100],
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
