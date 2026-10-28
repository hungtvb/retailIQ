"""Week 1 multi-agent harness: router, supervisor/subagents, handoff, skills.

Use full mode to run actual LangGraph/Chroma. Offline mode is a separate local
fallback and never reported as evidence of full LangGraph execution.
"""
from __future__ import annotations
from typing import Literal, TypedDict
import os
from contextlib import contextmanager
import atexit
import threading
from pathlib import Path
import sqlite3
from retailiq.assistant import intent, do
from retailiq.domain.analytics import month, products, top
from retailiq.core.config import chat_model, configure_langsmith
from retailiq.skills import skill_for, load_skill
from retailiq.observability import log_event, observed, request_id, session_id
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
    # Model answers may contain untrusted RAG text, multiple product names or
    # hallucinated SKUs. Only the user's own explicit reference may anchor a
    # follow-up; a top-seller question above uses reviewed SQL instead.
    from retailiq.assistant import product_sku
    for message in reversed(history or []):
        if message.get('role') != 'user':
            continue
        content = message.get('content', '')
        if not isinstance(content, str):
            continue
        sku = product_sku(content)
        if sku:
            return question + ' ' + sku
        if any(p['name'].casefold() in content.casefold() for p in products()):
            # Explicit but ambiguous reference => ask for a SKU; do not guess.
            return question
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
        proposed = getattr(parsed, 'intent', None)
        if proposed not in AGENT_FOR_INTENT:
            fallback = True
            log_event('agent.router_fallback', level='WARNING',
                      error_type='InvalidRouteDecision')
        elif category == 'product' or proposed == category:
            # Other categories are enforced by deterministic business routing.
            category = proposed
    except Exception as error:
        fallback = True
        log_event('agent.router_fallback', level='WARNING', error_type=type(error).__name__)
    target = AGENT_FOR_INTENT[category]
    previous = state.get('previous_agent', '')
    # A real agent-to-agent handoff: the former Sales Agent transfers control
    # with a typed Command, rather than merely labeling a router decision.
    if previous == 'sales_agent' and category == 'stock':
        target = 'sales_agent'
    log_event('agent.routed', agent=target, intent=category, route_fallback=fallback, execution_mode='full')
    return Command(update={'effective_question': effective, 'intent': category,
                           'route_fallback': fallback, 'skill': skill_for(category)}, goto=target)


def sales_agent(state: State):
    from langgraph.types import Command
    if state['intent'] == 'stock':
        log_event('agent.handoff', previous_agent='sales_agent', target_agent='inventory_agent', execution_mode='full')
        return Command(update={'handoff': {'from': 'sales_agent', 'to': 'inventory_agent',
                                           'reason': 'Follow-up inventory question'},
                               'active_agent': 'inventory_agent'}, goto='inventory_agent')
    # SQL KPI policy is enforced in reviewed functions, not an unused prompt.
    with observed('agent.sales', agent='sales_agent', execution_mode='full'):
        result = sales_analysis(state['effective_question'], state['intent'])
    return Command(update={**result, 'active_agent': 'sales_agent'}, goto='__end__')


def inventory_agent(state: State):
    from langgraph.types import Command
    # Inventory arithmetic is enforced by read-only SQL.
    with observed('agent.inventory', agent='inventory_agent', execution_mode='full'):
        result = inventory_analysis(state['effective_question'])
    return Command(update={**result, 'active_agent': 'inventory_agent'}, goto='__end__')


def product_agent(state: State):
    from langgraph.types import Command
    with observed('agent.product', agent='product_agent', execution_mode='full'):
        result = product_analysis(state['effective_question'])
    return Command(update={**result, 'active_agent': 'product_agent'}, goto='__end__')


def retail_supervisor(state: State):
    from langgraph.types import Command
    with observed('agent.supervisor', agent='retail_supervisor', execution_mode='full'):
        result = replenish_review(state['effective_question'])
    return Command(update={**result, 'active_agent': 'retail_supervisor'}, goto='__end__')


def retryable_read_failure(error: Exception) -> bool:
    """Only transient failures in idempotent read-only SQL paths are retryable."""
    return (isinstance(error, (ConnectionError, TimeoutError)) or
            (isinstance(error, sqlite3.OperationalError) and
             any(x in str(error).lower() for x in ('locked', 'busy'))))


def build_graph(*, checkpointer=None):
    from langgraph.graph import StateGraph, START, END
    from langgraph.types import Command, RetryPolicy
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
    # Minimal Week 1 resilience: retry only transient read failures, at most twice.
    read_retry = RetryPolicy(max_attempts=2, initial_interval=0.25,
                             jitter=False, retry_on=retryable_read_failure)
    graph.add_node('sales_agent', sales_agent, retry_policy=read_retry)
    graph.add_node('inventory_agent', inventory_agent, retry_policy=read_retry)
    graph.add_node('product_agent', product_agent)
    graph.add_node('retail_supervisor', retail_supervisor)
    graph.add_edge(START, 'router')
    # Control routing is Command-only: no accidental double-execution by static edges.
    return graph.compile(checkpointer=checkpointer)


def checkpoint_path() -> Path:
    return Path(os.getenv('RETAILIQ_CHECKPOINT_DB') or
                Path(__file__).resolve().parents[2] / 'data' / 'agent_checkpoints.sqlite3')


def delete_session_checkpoints(sid: str) -> None:
    """Logically remove a deleted chat's checkpoint state (local Week 1 only)."""
    if not checkpoint_path().exists():
        return
    # Requires the runtime package when old checkpoint data actually exists.
    # A failed deletion is surfaced to the API instead of silently leaking state.
    _session_graph().checkpointer.delete_thread(sid)


# Single-process/local graph. This is deliberately not a distributed store.
# A managed resource makes SQLite ownership/cleanup explicit, including test
# runs that change RETAILIQ_CHECKPOINT_DB between isolated fixtures.
_CHECKPOINT_CACHE_LOCK = threading.RLock()
_CHECKPOINT_CACHE: dict[str, object] = {}


def close_checkpoint_graph() -> None:
    """Close the owned SQLite connection and discard the cached graph.

    Do not call while a session request is executing. FastAPI shutdown/atexit
    can use this, and tests use it after any checkpoint-path changes.
    """
    with _CHECKPOINT_CACHE_LOCK:
        connection = _CHECKPOINT_CACHE.pop('connection', None)
        _CHECKPOINT_CACHE.clear()
        if connection is not None:
            connection.close()


atexit.register(close_checkpoint_graph)


def _session_graph():
    """One cached graph/connection for the configured local database path.

    A changing path is rejected instead of silently reusing a different
    conversation's checkpoints or closing a connection mid-request.
    """
    path = checkpoint_path().resolve()
    with _CHECKPOINT_CACHE_LOCK:
        existing = _CHECKPOINT_CACHE.get('path')
        if existing is not None:
            if existing != path:
                raise RuntimeError(
                    'Checkpoint database path changed during process lifetime; '
                    'close_checkpoint_graph() before reconfiguring')
            return _CHECKPOINT_CACHE['graph']
        from langgraph.checkpoint.sqlite import SqliteSaver
        path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(path), check_same_thread=False)
        try:
            compiled = build_graph(checkpointer=SqliteSaver(conn))
        except BaseException:
            conn.close()
            raise
        _CHECKPOINT_CACHE.update({'path': path, 'graph': compiled, 'connection': conn})
        return compiled


def run(q: str, *, history: list[dict] | None = None, active_agent: str = '') -> dict:
    configure_langsmith()
    sid = session_id()
    rid = request_id()
    config = {
        'run_name': 'RetailIQ-Week1-MultiAgent',
        'tags': ['retailiq', 'flezi-week1', 'multi-agent'],
        'metadata': {'request_id': rid or 'stateless',
                     'retailiq_session_id': sid or 'stateless'},
        'recursion_limit': 12,
    }
    if sid:
        config['configurable'] = {'thread_id': sid}
    inputs = {
        'question': q, 'history': (history or [])[-12:],
        'previous_agent': active_agent,
        'answer': '', 'records': [], 'contexts': [],
        'handoff': None, 'subagents': [], 'route_fallback': False,
    }
    graph = _session_graph() if sid else build_graph()
    if os.getenv('RETAILIQ_NATIVE_GRAPH_EVENTS', 'false').lower() in ('1', 'true', 'yes'):
        result = dict(inputs)
        for update in graph.stream(inputs, config=config, stream_mode='updates'):
            for node, values in update.items():
                if isinstance(values, dict):
                    result.update(values)
                log_event('graph.node_updated', agent=node, execution_mode='full')
        if not result.get('answer'):
            raise ValueError('Graph stream completed without a verified answer')
    else:
        result = graph.invoke(inputs, config=config)
    return {'question': q, 'intent': result['intent'],
            'mode': 'LangGraph Multi-Agent + SQL / Chroma RAG',
            'as_of': month(), 'answer': result['answer'],
            'records': result.get('records', []), 'contexts': result.get('contexts', []),
            'active_agent': result.get('active_agent', ''),
            'handoff': result.get('handoff'),
            'subagents': result.get('subagents', []),
            'skill': result.get('skill', ''),
            'route_fallback': result.get('route_fallback', False)}
