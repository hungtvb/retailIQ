"""Week 1 multi-agent harness: router, supervisor/subagents, handoff, skills.

Use full mode to run actual LangGraph/Chroma. Offline mode is a separate local
fallback and never reported as evidence of full LangGraph execution.
"""
from __future__ import annotations
from typing import Literal, TypedDict
import os
import re
from contextlib import contextmanager
import atexit
import threading
from pathlib import Path
import sqlite3
from retailiq.queries import (intent, do, product_sku, wants_single_latest_product,
                              requested_top_count, is_multi_stock_question, is_price_extreme)
from retailiq.reply import retailiq_reply
from retailiq.domain.analytics import month, products, requested_month, top
from retailiq.core.config import chat_model, configure_langsmith
from retailiq.skills import skill_for, load_skill
from retailiq.observability import log_event, observed, request_id, session_id
from retailiq.orchestration.agents import sales_analysis, inventory_analysis, product_analysis, replenish_review
from retailiq.domain.analytics import catalog_product, newest_products

AGENT_FOR_INTENT = {
    'stock': 'inventory_agent', 'revenue': 'sales_agent',
    'top': 'sales_agent', 'product': 'product_agent', 'decision': 'retail_supervisor',
    'general': 'retailiq',
    'latest': 'product_agent',
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
    period: str
    active_agent: str
    handoff: dict | None
    skill: str
    subagents: list[str]
    route_fallback: bool


def classify(question: str) -> str:
    q = question.casefold()
    if any(x in q for x in ('newest product', 'latest product', 'new products', 'sản phẩm mới nhất', 'sản phẩm mới', 'mẫu mới nhất')):
        return 'latest'
    sales = ('top seller', 'best seller', 'bán chạy', 'bestseller', 'selling most')
    stock = ('stock', 'inventory', 'tồn kho', 'available', 'replenish', 'reorder', 'restock', 'bổ sung')
    if any(x in q for x in ('replenishment review', 'inventory decision', 'bổ sung hàng bán chạy')):
        return 'decision'
    if any(x in q for x in sales) and any(x in q for x in stock):
        # Stock coverage is not a purchasing/replenishment recommendation.
        # Explicit action terms retain the supervisor route.
        if any(x in q for x in ('replenish', 'reorder', 'restock', 'bổ sung')):
            return 'decision'
        return 'stock'
    return intent(question)


def _referential(question: str) -> bool:
    return bool(re.search(r'\b(nó|đó|ấy|this|that|its|it|giá|price|bao nhiêu|how much)\b', question.casefold()))


def _previous_user_question(history: list[dict] | None) -> str:
    for message in reversed(history or []):
        if message.get('role') == 'user' and isinstance(message.get('content'), str):
            content = message['content']
            if classify(content) != 'general':
                return content
            if not _referential(content):
                break
    return ''


def followup_intent(question: str, history: list[dict] | None = None) -> str:
    """Infer only short, referential follow-ups from the last user turn."""
    category = classify(question)
    if category != 'general':
        return category
    prior = _previous_user_question(history)
    if prior and requested_month(question) != month() and classify(prior) in ('revenue', 'top'):
        return classify(prior)
    if not _referential(question):
        return category
    if prior and classify(prior) in ('product', 'latest', 'top', 'stock'):
        return 'product'
    return category


def resolve_followup(question: str, history: list[dict] | None = None,
                     category: str | None = None) -> str:
    """Supply a SKU only from user text or a deterministic catalog/sales result."""
    category = category or followup_intent(question, history)
    if category not in ('stock', 'product'):
        return question
    q = question.casefold()
    if any(p['sku'].casefold() in q or p['name'].casefold() in q for p in products()):
        return question
    if is_multi_stock_question(question):
        # Direct cross-domain question; do() retrieves the ranked group itself.
        return question
    # Only user-authored sales questions can define a ranked-stock reference.
    # Do not extract ambiguous SKUs from assistant-generated prose.
    previous = _previous_user_question(history)
    if category == 'stock' and previous and classify(previous) == 'top':
        ranked_count = requested_top_count(previous)
        ranked_period = requested_month(previous)
        rank = re.search(r'(?:đứng\s*thứ|xếp\s*thứ|rank(?:ed)?\s*#?)\s*(\d+)', q)
        if rank:
            index = int(rank.group(1)) - 1
            if not 0 <= index < ranked_count:
                # Explicitly invalid reference: preserve the question so the
                # stock lookup asks for clarification. Never fall through to
                # the first seller from the previous turn.
                return question
            ranked = top(ranked_period)
            if index >= len(ranked):
                return question
            return question + ' ' + ranked[index]['sku']
        references_group = any(marker in q for marker in (
            'các sản phẩm đó', 'các sản phẩm ấy', 'những sản phẩm đó',
            'those products', 'these products', 'all of them'))
        references_group |= bool(re.search(
            r'\b(their|those|these|them)\b', q
        ))
        if references_group:
            return f'Stock for top {ranked_count} best sellers in {ranked_period}'
    if 'top seller' in q or 'best seller' in q or 'bán chạy' in q:
        ranked = top(requested_month(question))
        return question + (' ' + ranked[0]['sku'] if ranked else '')
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
        previous_category = classify(content)
        if previous_category == 'latest':
            rows = newest_products(1)
            return question + (' ' + rows[0]['sku'] if rows else '')
        if previous_category == 'top':
            rows = top(requested_month(content))
            return question + (' ' + rows[0]['sku'] if rows else '')
        if previous_category == 'general' and not _referential(content):
            return question
        if any(p['name'].casefold() in content.casefold() for p in products()):
            # Explicit but ambiguous reference => ask for a SKU; do not guess.
            return question
    return question


def route(state: State):
    """A router chooses a specialist; no raw LLM response can execute SQL."""
    from pydantic import BaseModel
    from langgraph.types import Command

    class Route(BaseModel):
        intent: Literal['stock', 'revenue', 'top', 'product', 'decision', 'general', 'latest']

    category = followup_intent(state['question'], state.get('history', []))
    effective = resolve_followup(state['question'], state.get('history', []), category)
    fallback = False
    try:
        parsed = chat_model().with_structured_output(Route).invoke([
            ('system', 'Route retail requests to stock/revenue/top/product/decision/latest/general. '
             'Use decision only when cross-analyzing bestsellers and inventory. '
             'Never execute side effects.'),
            ('human', state['question']),
        ])
        proposed = getattr(parsed, 'intent', None)
        if proposed not in AGENT_FOR_INTENT:
            fallback = True
            log_event('agent.router_fallback', level='WARNING',
                      error_type='InvalidRouteDecision')
        elif proposed == category:
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
    selected_skill = skill_for(category)
    if selected_skill:
        # Routing/selection is not proof of loading or executing a skill.
        log_event('skill.selected', agent=AGENT_FOR_INTENT[category],
                  skill=selected_skill, execution_mode='full')
    return Command(update={'effective_question': effective, 'intent': category,
                           'route_fallback': fallback, 'skill': selected_skill}, goto=target)


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
    return Command(update={**result, 'active_agent': 'sales_agent'}, goto='retailiq_reply')


def inventory_agent(state: State):
    from langgraph.types import Command
    # Inventory arithmetic is enforced by read-only SQL.
    with observed('agent.inventory', agent='inventory_agent', execution_mode='full'):
        result = inventory_analysis(state['effective_question'])
    return Command(update={**result, 'active_agent': 'inventory_agent'}, goto='retailiq_reply')


def product_agent(state: State):
    from langgraph.types import Command
    with observed('agent.product', agent='product_agent', execution_mode='full'):
        if state['intent'] == 'latest':
            result = {'answer': '', 'records': newest_products(1 if wants_single_latest_product(state['question']) else 5), 'contexts': [],
                      'skill': 'catalog_lookup', 'agent': 'product_agent'}
        elif is_price_extreme(state['effective_question']):
            result = {**do(state['effective_question'], 'product'),
                      'skill': 'catalog_lookup', 'agent': 'product_agent'}
        elif any(word in state['question'].casefold() for word in ('giá', 'price', 'cost')) and product_sku(state['effective_question']):
            item = catalog_product(product_sku(state['effective_question']))
            result = {'answer': '', 'records': [item] if item else [], 'contexts': [],
                      'skill': 'catalog_lookup', 'agent': 'product_agent'}
        else:
            result = product_analysis(state['effective_question'])
    return Command(update={**result, 'active_agent': 'product_agent'}, goto='retailiq_reply')


def retail_supervisor(state: State):
    from langgraph.types import Command
    with observed('agent.supervisor', agent='retail_supervisor', execution_mode='full'):
        result = replenish_review(state['effective_question'])
    return Command(update={**result, 'active_agent': 'retail_supervisor'}, goto='retailiq_reply')


def retailiq(state: State):
    """Handle conversation without sending ordinary chat to product retrieval."""
    from langgraph.types import Command
    reply = chat_model().invoke([
        ('system', 'You are RetailIQ, a helpful retail assistant. Reply in the language of the user question. '
         'For greetings and ordinary conversation, answer naturally. Do not invent inventory, sales, '
         'product specifications, prices, or policies. Ask for a specific retail question when data is needed.'),
        ('human', state['question']),
    ])
    answer = getattr(reply, 'content', '')
    if not isinstance(answer, str) or not answer.strip():
        raise ValueError('RetailIQ returned an empty answer')
    return Command(update={'answer': answer, 'active_agent': 'retailiq', 'records': [], 'contexts': []},
                   goto='retailiq_reply')


def retryable_read_failure(error: Exception) -> bool:
    """Only transient failures in idempotent read-only SQL paths are retryable."""
    return (isinstance(error, (ConnectionError, TimeoutError)) or
            (isinstance(error, sqlite3.OperationalError) and
             any(x in str(error).lower() for x in ('locked', 'busy'))))


def build_graph(*, checkpointer=None):
    from langgraph.graph import StateGraph, START, END
    from langgraph.types import RetryPolicy
    graph = StateGraph(State)
    # Declare Command destinations on the graph nodes, not by mutating shared
    # Python function annotations on every build (unsafe with concurrent builds).
    graph.add_node('router', route,
                   destinations=tuple(dict.fromkeys(AGENT_FOR_INTENT.values())))
    # Only read-only SQL agents may retry a transient operational failure.
    read_retry = RetryPolicy(max_attempts=2, initial_interval=0.25,
                             jitter=False, retry_on=retryable_read_failure)
    graph.add_node('sales_agent', sales_agent, retry_policy=read_retry,
                   destinations=('inventory_agent', 'retailiq_reply'))
    graph.add_node('inventory_agent', inventory_agent, retry_policy=read_retry,
                   destinations=('retailiq_reply',))
    graph.add_node('product_agent', product_agent, destinations=('retailiq_reply',))
    graph.add_node('retail_supervisor', retail_supervisor, destinations=('retailiq_reply',))
    graph.add_node('retailiq', retailiq, destinations=('retailiq_reply',))
    graph.add_node('retailiq_reply', retailiq_reply)
    graph.add_edge('retailiq_reply', END)
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



def bounded_history(history: list[dict] | None) -> list[dict]:
    """Persist only user-authored follow-up evidence, not model/HTML output.

    The Week 1 router uses previous user product identifiers only; carrying
    12 large assistant answers in every checkpoint wastes disk and increases
    the attack surface without adding useful routing context.
    """
    if history is None:
        return []
    if not isinstance(history, list):
        raise ValueError('Chat history must be a list')
    output = []
    for item in history[-24:]:
        if not isinstance(item, dict) or item.get('role') != 'user':
            continue
        content = item.get('content')
        if isinstance(content, str) and content.strip():
            output.append({'role': 'user', 'content': content[:500]})
    return output[-12:]


class GraphResultError(ValueError):
    """Graph finished without a complete, correctly routed business result."""


def validate_graph_result(result: dict) -> dict:
    """Do not leak incomplete state or label one agent's output as another."""
    if not isinstance(result, dict):
        raise GraphResultError('Graph result is not an object')
    category = result.get('intent')
    agent = result.get('active_agent')
    if category not in AGENT_FOR_INTENT or agent != AGENT_FOR_INTENT[category]:
        raise GraphResultError('Graph result has inconsistent intent and agent')
    answer = result.get('answer')
    if not isinstance(answer, str) or not answer.strip() or len(answer) > 20_000:
        raise GraphResultError('Graph result has no valid bounded answer')
    if not isinstance(result.get('records', []), list) or not isinstance(result.get('contexts', []), list):
        raise GraphResultError('Graph result has invalid evidence collections')
    handoff = result.get('handoff')
    if handoff is not None:
        if (not isinstance(handoff, dict) or
                handoff.get('from') != 'sales_agent' or
                handoff.get('to') != 'inventory_agent' or
                agent != 'inventory_agent'):
            raise GraphResultError('Graph result has an invalid handoff')
    return result


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
        'question': q, 'history': bounded_history(history),
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
    result = validate_graph_result(result)
    return {'question': q, 'intent': result['intent'],
            'mode': 'LangGraph Multi-Agent + SQL / Chroma RAG',
            'as_of': result.get('period', month()), 'answer': result['answer'],
            'records': result.get('records', []), 'contexts': result.get('contexts', []),
            'active_agent': result.get('active_agent', ''),
            'handoff': result.get('handoff'),
            'subagents': result.get('subagents', []),
            'skill': result.get('skill', ''),
            'route_fallback': result.get('route_fallback', False)}
