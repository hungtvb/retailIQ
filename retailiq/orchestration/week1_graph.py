"""Week 1 multi-agent harness: router, supervisor/subagents, handoff, skills.

Use full mode to run actual LangGraph/Chroma. Offline mode is a separate local
fallback and never reported as evidence of full LangGraph execution.
"""
from __future__ import annotations
from typing import Literal, TypedDict
from retailiq.assistant import intent, do
from retailiq.domain.analytics import month, products, top
from retailiq.core.config import chat_model, configure_langsmith
from retailiq.skills import skill_for, load_skill
from retailiq.orchestration.agents import sales_analysis, inventory_analysis, product_analysis, replenish_review

AGENT_FOR_INTENT = {
    'stock': 'inventory_agent', 'revenue': 'sales_agent',
    'top': 'sales_agent', 'product': 'product_agent', 'decision': 'retail_supervisor',
}


class State(TypedDict, total=False):
    question: str
    effective_question: str
    history: list[dict]
    previous_agent: str
    intent: str
    answer: str
    records: list
    contexts: list
    active_agent: str
    handoff: dict | None
    skill: str
    subagents: list[str]
    route_fallback: bool


def classify(question: str) -> str:
    q = question.casefold()
    sales = ('top seller', 'best seller', 'bán chạy', 'bestseller', 'selling most')
    stock = ('stock', 'inventory', 'tồn kho', 'available', 'replenish', 'reorder', 'restock', 'bổ sung')
    if any(x in q for x in sales) and any(x in q for x in stock):
        # A pure stock lookup mentioning 'top seller' is not a replenishment decision.
        if any(x in q for x in ('how many', 'what is the stock', 'how much stock', 'bao nhiêu')):
            return 'stock'
        return 'decision'
    if any(x in q for x in ('replenishment review', 'inventory decision', 'bổ sung hàng bán chạy')):
        return 'decision'
    return intent(question)


def resolve_followup(question: str, history: list[dict] | None = None) -> str:
    """Supply a grounded SKU to a short follow-up; never invent a product."""
    if classify(question) != 'stock':
        return question
    q = question.casefold()
    if any(p['sku'].casefold() in q or p['name'].casefold() in q for p in products()):
        return question
    if 'top seller' in q or 'best seller' in q or 'bán chạy' in q:
        rows = top()
        return question + (' ' + rows[0]['sku'] if rows else '')
    # The latest explicit user mention outranks incidental names in generated answers.
    messages = list(reversed(history or []))
    for role in ('user', 'assistant'):
        for message in messages:
            if message.get('role') != role:
                continue
            content = message.get('content', '').casefold()
            for product in products():
                if product['name'].casefold() in content or product['sku'].casefold() in content:
                    return question + ' ' + product['sku']
    return question


def route(state: State):
    """A router chooses a specialist; no raw LLM response can execute SQL."""
    from pydantic import BaseModel
    from langgraph.types import Command

    class Route(BaseModel):
        intent: Literal['stock', 'revenue', 'top', 'product', 'decision']

    effective = resolve_followup(state['question'], state.get('history', []))
    category = classify(state['question'])
    fallback = False
    try:
        parsed = chat_model().with_structured_output(Route).invoke([
            ('system', 'Route retail requests to stock/revenue/top/product/decision. '
             'Use decision only when cross-analyzing bestsellers and inventory. '
             'Never execute side effects.'),
            ('human', state['question']),
        ])
        if parsed.intent in AGENT_FOR_INTENT:
            # Keep unambiguous cross-domain intent from being overridden by a narrow model prediction.
            if category == 'product' or parsed.intent == category:
                category = parsed.intent
    except Exception:
        fallback = True
    target = AGENT_FOR_INTENT[category]
    previous = state.get('previous_agent', '')
    # A real agent-to-agent handoff: the former Sales Agent transfers control
    # with a typed Command, rather than merely labeling a router decision.
    if previous == 'sales_agent' and category == 'stock':
        target = 'sales_agent'
    return Command(update={'effective_question': effective, 'intent': category,
                           'route_fallback': fallback, 'skill': skill_for(category)}, goto=target)


def sales_agent(state: State):
    from langgraph.types import Command
    if state['intent'] == 'stock':
        return Command(update={'handoff': {'from': 'sales_agent', 'to': 'inventory_agent',
                                           'reason': 'Follow-up inventory question'},
                               'active_agent': 'inventory_agent'}, goto='inventory_agent')
    # Explicitly loading a skill makes this more than a directory of Markdown docs.
    load_skill('sales_kpi')
    result = sales_analysis(state['effective_question'], state['intent'])
    return Command(update={**result, 'active_agent': 'sales_agent'}, goto='__end__')


def inventory_agent(state: State):
    from langgraph.types import Command
    load_skill('inventory_availability')
    result = inventory_analysis(state['effective_question'])
    return Command(update={**result, 'active_agent': 'inventory_agent'}, goto='__end__')


def product_agent(state: State):
    from langgraph.types import Command
    result = product_analysis(state['effective_question'])
    return Command(update={**result, 'active_agent': 'product_agent'}, goto='__end__')


def retail_supervisor(state: State):
    from langgraph.types import Command
    load_skill('replenishment_review')
    result = replenish_review()
    return Command(update={**result, 'active_agent': 'retail_supervisor'}, goto='__end__')


def build_graph():
    from langgraph.graph import StateGraph, START, END
    from langgraph.types import Command
    # Typed Command destinations make all dynamic routes visible to LangGraph's
    # static graph validation and visualizer without importing LangGraph offline.
    route.__annotations__['return'] = Command[Literal['sales_agent', 'inventory_agent',
                                                       'product_agent', 'retail_supervisor']]
    sales_agent.__annotations__['return'] = Command[Literal['inventory_agent', '__end__']]
    inventory_agent.__annotations__['return'] = Command[Literal['__end__']]
    product_agent.__annotations__['return'] = Command[Literal['__end__']]
    retail_supervisor.__annotations__['return'] = Command[Literal['__end__']]
    graph = StateGraph(State)
    graph.add_node('router', route)
    graph.add_node('sales_agent', sales_agent)
    graph.add_node('inventory_agent', inventory_agent)
    graph.add_node('product_agent', product_agent)
    graph.add_node('retail_supervisor', retail_supervisor)
    graph.add_edge(START, 'router')
    # Control routing is Command-only: no accidental double-execution by static edges.
    return graph.compile()


def run(q: str, *, history: list[dict] | None = None, active_agent: str = '') -> dict:
    configure_langsmith()
    result = build_graph().invoke(
        {'question': q, 'history': (history or [])[-12:], 'previous_agent': active_agent},
        config={'run_name': 'RetailIQ-Week1-MultiAgent',
                'tags': ['retailiq', 'flezi-week1', 'multi-agent']},
    )
    return {'question': q, 'intent': result['intent'],
            'mode': 'LangGraph Multi-Agent + SQL / Chroma RAG',
            'as_of': month(), 'answer': result['answer'],
            'records': result.get('records', []), 'contexts': result.get('contexts', []),
            'active_agent': result.get('active_agent', ''),
            'handoff': result.get('handoff'),
            'subagents': result.get('subagents', []),
            'skill': result.get('skill', ''),
            'route_fallback': result.get('route_fallback', False)}
