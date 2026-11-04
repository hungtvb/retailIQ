"""Week 1 multi-agent harness: router, supervisor/subagents, handoff, skills.

Use full mode to run actual LangGraph/Chroma. Offline mode is a separate local
fallback and never reported as evidence of full LangGraph execution.
"""
from __future__ import annotations
from typing import Literal, TypedDict
from functools import lru_cache
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
    'general': 'retailiq', 'backorder': 'backorder_agent',
    'latest': 'product_agent', 'fiction_stock': 'fiction_inventory_agent',
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
    query_plan: dict
    customer_memory: dict
    disposition: str
    evidence_refs: list[str]
    findings: list[dict]
    limitations: list[str]
    approval_status: str
    reason_codes: list[str]
    source: dict
    capability_plan: dict
    temporal: dict
    verified_case_context: dict | None
    uc01_followup_kind: str | None
    fiction_product: str | None
    fiction_warehouse: str | None


def classify(question: str) -> str:
    q = question.casefold()
    # CASE-ID is the required, explicit UC-01 fast-path selector; malformed IDs
    # must reach the bounded validator rather than a generic LLM answer.
    if 'case-' in q:
        return 'backorder'
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


_FR_SKU_MATCH = re.compile(r"(?<![A-Za-z0-9-])FR-[0-9A-F]{16}(?![A-Za-z0-9-])")
_UUID_IN_QUESTION = re.compile(r"(?<![A-Za-z0-9])(?:[0-9a-f]{8}-)(?:[0-9a-f]{4}-){3}[0-9a-f]{12}(?![A-Za-z0-9])", re.I)


def _fiction_inventory_request(question: str) -> tuple[str, str | None] | None:
    """Only explicit single-FR-SKU stock questions enter the new MCP path."""
    lower = question.casefold()
    stock_words = ('stock', 'inventory', 'tồn kho', 'còn hàng', 'available', 'còn bao nhiêu')
    if 'case-' in lower or not any(token in lower for token in stock_words) or 'fr-' not in lower:
        return None
    matches = _FR_SKU_MATCH.findall(question.upper())
    if len(matches) != 1 or question.casefold().count('fr-') != 1:
        raise InvalidFictionScope('Exactly one complete FR-SKU is required for Fiction inventory')
    # The undated stock table cannot answer historical/live source-time questions.
    if any(token in lower for token in (
            'hiện tại', 'ngay lúc này', 'hôm nay', 'hôm qua', 'tuần trước',
            'tháng trước', ' at 20', ' on 20', 'as of', 'today', 'yesterday', 'now',
            'right now', 'current', 'live', 'realtime', 'real-time')):
        raise InvalidFictionScope('UNSUPPORTED_TEMPORAL_SCOPE: Fiction stock has no observation timestamp')
    from retailiq.domain.fiction import _id
    wants_warehouse = 'warehouse' in lower or 'kho ' in lower
    ids = _UUID_IN_QUESTION.findall(question)
    if wants_warehouse and len(ids) != 1:
        raise InvalidFictionScope('Specify exactly one warehouse UUID or omit warehouse filter')
    if ids and not wants_warehouse:
        raise InvalidFictionScope('Unscoped UUID in Fiction inventory question')
    warehouse = _id(ids[0]) if ids else None
    return matches[0], warehouse


def route(state: State):
    """A router chooses a specialist; no raw LLM response can execute SQL."""
    from pydantic import BaseModel
    from langgraph.types import Command

    class Route(BaseModel):
        intent: Literal['stock', 'revenue', 'top', 'product', 'decision', 'general', 'latest', 'backorder']

    fiction_stock = _fiction_inventory_request(state['question'])
    if fiction_stock is not None:
        return Command(update={'effective_question': state['question'], 'intent': 'fiction_stock',
                               'fiction_product': fiction_stock[0],
                               'fiction_warehouse': fiction_stock[1],
                               'route_fallback': False, 'skill': ''},
                       goto='fiction_inventory_agent')

    uc01_kind = _uc01_followup_kind(state['question'])
    if uc01_kind == 'ambiguous_warehouse':
        raise UnresolvedCaseReference('Specify the warehouse ID; its display position is not verified')
    if uc01_kind is not None:
        committed = state.get('verified_case_context')
        if not isinstance(committed, dict):
            raise UnresolvedCaseReference('Specify an explicit CASE-ID; no committed case reference is available')
        # This binding was loaded from the latest committed assistant turn in
        # the current session, not from graph checkpoints or model text.
        log_event('context.case_resolved', intent='backorder', execution_mode='full',
                  source='committed_session_case')
        return Command(update={
            'effective_question': state['question'], 'intent': 'backorder',
            'route_fallback': False, 'skill': '', 'uc01_followup_kind': uc01_kind,
        }, goto='backorder_agent')

    category = followup_intent(state['question'], state.get('history', []))
    # Do not send malformed/ambiguous case IDs to a paid model or business tool.
    if category == 'backorder':
        _case_id_for_uc01(state['question'])
    effective = resolve_followup(state['question'], state.get('history', []), category)
    fallback = False
    try:
        parsed = chat_model().with_structured_output(Route).invoke([
            ('system', 'Route retail requests to stock/revenue/top/product/decision/latest/general/backorder. '
             'Use decision only when cross-analyzing bestsellers and inventory. '
             'Use backorder for investigations with an explicit CASE-UUID. '
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
        else:
            fallback = True
            log_event('agent.router_disagreement', level='WARNING',
                      proposed_intent=proposed, enforced_intent=category,
                      execution_mode='full')
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
    # UC-01 uses a vetted capability, not a legacy skill file.
    selected_skill = '' if category == 'backorder' else skill_for(category)
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
    from retailiq.domain.customer_memory import is_memory_question, memory_answer
    if is_memory_question(state['question']):
        return Command(update={
            'answer': memory_answer(state['question'], state.get('customer_memory')),
            'active_agent': 'retailiq', 'records': [], 'contexts': [],
        }, goto='retailiq_reply')
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



# UC-01 is the first explicitly bounded Fiction capability template.
# The generic capability-based planner in issue #23 is still pending.
_BACKORDER_CAPABILITY = "fiction.backorder.investigate"
_CASE_ID = re.compile(
    r"(?<![A-Za-z0-9])CASE-[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}(?![A-Za-z0-9])",
    re.IGNORECASE,
)


class InvalidCaseId(ValueError):
    """Invalid/ambiguous UC-01 input, not a provider or data-source failure."""


class InvalidFictionScope(InvalidCaseId):
    """Invalid or unsupported Fiction inventory query constraint (HTTP 422)."""




class UnresolvedCaseReference(InvalidCaseId):
    """Case/warehouse reference requires clarification or current-source review."""


def _uc01_followup_kind(question: str) -> str | None:
    """Small conservative UC-01 anaphora grammar, never a policy/entity oracle."""
    q = ' '.join(question.casefold().split())
    if len(q) > 160:
        return None
    # A numbered warehouse has no authority unless its displayed order was
    # committed; no such ordering is persisted in this first T03 slice.
    if re.search(r'kho\s+(?:thứ\s*(?:hai|2)|số\s*2)|(?:second|2nd)\s+warehouse', q):
        return 'ambiguous_warehouse'
    if 'case-' in q:
        return None  # Explicit CASE-ID uses the original reviewed T02 route.
    if any(term in q for term in ('refund', 'return', 'hoàn tiền', 'đổi trả',
                                  'bảo hành', 'pricing', 'chính sách giá')):
        return None  # A topic switch must not inherit a previous case.
    if (('đơn hàng này' in q or 'đơn này' in q or 'this order' in q) and
            any(token in q for token in ('gồm', 'sản phẩm', 'chi tiết', 'items', 'lines', 'details', 'contain'))):
        return 'order_details'
    if (('chính sách' in q and any(x in q for x in ('áp dụng', 'nào', 'đó')))
            or ('policy' in q and any(x in q for x in ('appl', 'which', 'warehouse', 'transfer')))):
        return 'policy'
    if any(x in q for x in ('kho khác', 'còn kho', 'kho nào khác',
                           'other warehouse', 'another warehouse',
                           'alternative warehouse', 'other warehouses')):
        return 'alternatives'
    return None


def _case_id_for_uc01(question: str) -> str:
    matches = _CASE_ID.findall(question)
    if len(matches) != 1 or question.casefold().count("case-") != 1:
        raise InvalidCaseId("UC-01 requires exactly one explicit canonical CASE-ID")
    return "CASE-" + matches[0][5:].lower()


@lru_cache(maxsize=2)
def _fiction_store_cached(db: str, manifest: str):
    # Opening a store validates the full pinned release once. Its _q still
    # rejects file replacement or unverified WAL sidecars on each business read.
    from retailiq.domain.fiction import FictionStore
    return FictionStore.open(db, manifest)


def _uc01_inputs():
    root = Path(__file__).resolve().parents[2]
    db = os.getenv("RETAILIQ_FICTION_DB") or str(root / "data/fiction/fiction_retail.sqlite")
    manifest = os.getenv("RETAILIQ_FICTION_MANIFEST") or str(root / "data/fiction/manifest.json")
    knowledge = os.getenv("RETAILIQ_FICTION_KNOWLEDGE_ROOT") or str(root / "data/fiction/knowledge")
    return db, manifest, knowledge


def fiction_inventory_agent(state: State):
    """One explicit FR-SKU read through actual verified stdio MCP."""
    from langgraph.types import Command
    from retailiq.mcp_adapter import read_fiction_inventory
    from retailiq.language import is_vietnamese

    product = state["fiction_product"]
    warehouse = state.get("fiction_warehouse")
    result = read_fiction_inventory(product, warehouse)
    rows = result["data"]
    limits = result["limitations"]
    vi = is_vietnamese(state["question"])
    if not rows:
        reason = (limits[-1] if limits else "NO_INVENTORY_RECORDS")
        answer = (f"Không có bằng chứng tồn kho xác thực cho {product}: {reason}. "
                  "Không thể suy ra số lượng bằng 0."
                  if vi else f"No verified inventory rows for {product}: {reason}. "
                  "Missing evidence is not zero.")
    else:
        details = "; ".join(
            f"{r['warehouse_id']}: {r['available_snapshot']}" for r in rows
        )
        answer = (f"Bản ghi tồn kho không có thời điểm quan sát cho {product}: {details}. "
                  "Đây KHÔNG phải tồn kho hiện tại hoặc tại một thời điểm lịch sử."
                  if vi else
                  f"Undated recorded stock for {product}: {details}. "
                  "This does NOT prove current or historical stock.")
    return Command(update={
        "intent": "fiction_stock", "answer": answer, "active_agent": "fiction_inventory_agent",
        "records": rows, "contexts": [], "source": result["source"],
        "evidence_refs": result["record_refs"], "limitations": limits,
        "temporal": result["temporal"], "approval_status": None,
    }, goto="retailiq_reply")


def backorder_agent(state: State):
    """Run one vetted read-only UC-01 capability; no policy or case LLM authority."""
    from langgraph.types import Command
    from retailiq.domain.backorder import investigate_backorder
    from retailiq.language import is_vietnamese

    followup = state.get('uc01_followup_kind')
    committed = state.get('verified_case_context') if followup else None
    if followup:
        if not isinstance(committed, dict) or not isinstance(committed.get('case_id'), str):
            raise UnresolvedCaseReference('Verified CASE-ID is required for this follow-up')
        case_id = _case_id_for_uc01(committed['case_id'])
    else:
        case_id = _case_id_for_uc01(state['question'])
    db, manifest, knowledge = _uc01_inputs()
    log_event('capability.selected', agent='backorder_agent',
              capability=_BACKORDER_CAPABILITY, execution_mode='full')
    with observed('tool.sql', agent='backorder_agent',
                  tool=_BACKORDER_CAPABILITY, execution_mode='full'):
        investigation = investigate_backorder(
            _fiction_store_cached(db, manifest), case_id, knowledge_root=knowledge
        )

    if followup and (investigation['source']['id'] != committed['source_id']
                     or investigation['source']['version'] != committed['source_version']
                     or investigation['source']['sha256'] != committed['source_sha256']
                     or investigation['temporal']['evidence_cutoff'] != committed['cutoff']
                     or f"fulfillment_cases/{case_id}" != committed['case_ref']):
        raise UnresolvedCaseReference(
            'Historical case source/cutoff changed; please investigate the CASE-ID again')
    data = investigation['data']
    candidates = data['evidence_candidates']
    cutoff = data['cutoff']
    reasons = investigation['reason_codes']
    disposition = investigation['disposition']
    vi = is_vietnamese(state['question'])
    snapshots = {s['snapshot_id']: s for s in data['snapshots']}
    records = [
        {'case_id': case_id, 'cutoff': cutoff, 'snapshot_id': item['snapshot_id'],
         'warehouse_id': item['warehouse_id'],
         'observed_at': snapshots[item['snapshot_id']]['observed_at'],
         'received_at': snapshots[item['snapshot_id']]['received_at'],
         'available_at_observation': item['available_at_observation']}
        for item in candidates
    ]
    if followup == 'order_details':
        from retailiq.mcp_adapter import read_fiction_order
        case = data['case']
        order_detail = read_fiction_order(case['order_id'])
        o = order_detail['data']
        if (order_detail['source'] != investigation['source'] or
                order_detail['scope'].get('order_id') != case['order_id'] or
                not isinstance(o, dict) or
                len([line for line in o['lines'] if
                     line['order_item_id'] == case['order_item_id'] and
                     line['product_id'] == case['product_id'] and
                     line['quantity'] >= case['request_qty']]) != 1):
            raise UnresolvedCaseReference('Order/case identity or source changed')
        items = '; '.join(f"{line['product_id']}: {line['quantity']}" for line in o['lines'])
        answer = (f"Đơn {case['order_id']} gồm: {items}. Đây là dữ liệu đơn hàng tại bản phát hành; "
                  "trạng thái giao hàng KHÔNG phải trạng thái tại cutoff lịch sử."
                  if vi else
                  f"Order {case['order_id']} lines: {items}. Release-recorded shipment/order "
                  "state is NOT a historical state at the backorder cutoff.")
    elif followup == 'policy' and data['policy'] and data['policy']['applicable_at_cutoff']:
        policy = data['policy']
        answer = (f"Case {case_id} tại {cutoff}: chính sách {policy['policy_id']} có hiệu lực "
                  "và yêu cầu Manager phê duyệt đề xuất chuyển kho; chưa có chuyển kho nào được thực hiện."
                  if vi else
                  f"Case {case_id} at {cutoff}: policy {policy['policy_id']} applies and "
                  "requires Manager review for a transfer proposal; no transfer has occurred.")
    elif 'POLICY_CONFLICT' in reasons:
        answer = (f'Case {case_id} tại {cutoff}: các chính sách kho mâu thuẫn; cần xác minh quyền áp dụng. '
                  'Không có đề xuất chuyển kho được phê duyệt.'
                  if vi else
                  f'Case {case_id} at {cutoff}: warehouse policy authority conflicts. '
                  'Policy review is required; no transfer is approved.')
    elif disposition == 'NEEDS_REVIEW':
        details = '; '.join(
            f"{x['warehouse_id']} ({x['available_at_observation']})" for x in candidates[:5]
        )
        answer = (f'Case {case_id} tại {cutoff}: kho thay thế có bằng chứng đủ điều kiện: {details}. '
                  'Đây chỉ là đề xuất, cần Manager phê duyệt; không phải tồn kho hiện tại.'
                  if vi else
                  f'Case {case_id} at {cutoff}: case-evidenced alternative warehouse candidates: {details}. '
                  'Manager review is required; this is not current stock or an approved transfer.')
    elif disposition == 'SUPPORTED':
        answer = (f'Case {case_id} tại {cutoff}: không có ứng viên hợp lệ trong các kho thay thế '
                  'đã được ghi nhận và đánh giá. Không thể suy ra toàn bộ kho của doanh nghiệp hết hàng.'
                  if vi else
                  f'Case {case_id} at {cutoff}: no eligible alternative among evaluated case-recorded '
                  'warehouses. This does not prove company-wide unavailability.')
    else:
        answer = (f'Case {case_id} tại {cutoff}: chưa đủ bằng chứng để kết luận khả năng chuyển kho. '
                  f'Thiếu/hạn chế: {", ".join(reasons)}. Không được suy ra tồn kho bằng 0.'
                  if vi else
                  f'Case {case_id} at {cutoff}: insufficient transfer evidence ({", ".join(reasons)}). '
                  'Missing evidence is not zero available inventory.')

    evidence_refs = investigation['record_refs'][:100]
    # Case/stock findings remain usable even if a policy document is missing
    # or in conflict; only attach policy lineage when its applicability passed.
    policy_ref = ([f"knowledge_documents/{data['policy']['document_id']}"]
                  if data['policy'] and data['policy']['applicable_at_cutoff'] else [])
    findings = [
        {'text': f"Alternative warehouse {r['warehouse_id']}: "
                 f"{r['available_at_observation']} units in observation at {r['observed_at']}, "
                 f"received at {r['received_at']}; verified evidence at cutoff {cutoff}",
         'evidence_refs': [f"inventory_snapshots_v2/{r['snapshot_id']}",
                           f"warehouse_eligibility/{case_id}/{r['warehouse_id']}"] + policy_ref}
        for r in records
    ]
    if followup == 'order_details':
        evidence_refs = list(dict.fromkeys(evidence_refs + order_detail["record_refs"]))[:100]
        records = [dict(line) for line in order_detail["data"]["lines"]]
        findings = [{
            "text": ("Order lines recorded in the Fiction release; "
                     "shipment/order state not verified at case cutoff"),
            "evidence_refs": order_detail["record_refs"][:20],
        }]
    if followup == 'policy' and policy_ref:
        findings = [{
            'text': f"Warehouse policy {data['policy']['policy_id']} applies at {cutoff}; "
                    "Manager approval required for a proposed transfer",
            'evidence_refs': [
                f"fulfillment_policies/{data['policy']['policy_id']}", *policy_ref],
        }]
    if not findings:
        findings = [{'text': 'No eligible alternative in evaluated case records'
                     if disposition == 'SUPPORTED' else 'Transfer feasibility is not verified',
                     'evidence_refs': evidence_refs[:20]}]

    return Command(update={
        'answer': answer, 'records': records, 'contexts': [],
        'active_agent': 'backorder_agent',
        'disposition': disposition, 'evidence_refs': evidence_refs,
        'findings': findings, 'limitations': investigation['limitations'],
        'approval_status': investigation['approval_status'],
        'reason_codes': reasons, 'source': investigation['source'],
        'temporal': investigation['temporal'],
        'capability_plan': {'kind': 'fixed_uc01',
                            'capabilities': ([_BACKORDER_CAPABILITY, 'mcp.order_lookup']
                                             if followup == 'order_details' else [_BACKORDER_CAPABILITY]),
                            'case_id': case_id,
                            'source': ('committed_session_case' if followup
                                       else 'validated_explicit_case_id'),
                            'source_request_id': committed.get('source_request_id') if followup else None},
    }, goto='retailiq_reply')

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
    graph.add_node('fiction_inventory_agent', fiction_inventory_agent,
                   destinations=('retailiq_reply',))
    graph.add_node('backorder_agent', backorder_agent, retry_policy=read_retry,
                   destinations=('retailiq_reply',))
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
    if category == 'backorder':
        if result.get('disposition') not in {'SUPPORTED', 'NEEDS_REVIEW', 'INSUFFICIENT_EVIDENCE'}:
            raise GraphResultError('Backorder business disposition is not verified')
        if result.get('approval_status') != 'NOT_REQUESTED':
            raise GraphResultError('Backorder approval cannot be inferred by the model')
        if (not isinstance(result.get('evidence_refs'), list) or
                not isinstance(result.get('findings'), list) or
                not isinstance(result.get('source'), dict) or
                result.get('capability_plan', {}).get('capabilities') not in (
                    [_BACKORDER_CAPABILITY], [_BACKORDER_CAPABILITY, 'mcp.order_lookup'])):
            raise GraphResultError('Backorder case response lacks verified evidence lineage')
    if category == 'fiction_stock':
        if (not isinstance(result.get('source'), dict) or
                not isinstance(result.get('evidence_refs'), list) or
                not isinstance(result.get('limitations'), list) or
                not any('UNDATED_INVENTORY' in x for x in result['limitations'])):
            raise GraphResultError('Fiction inventory lacks verified undated evidence')
    if category == 'revenue' and result.get('query_plan') is not None:
        from retailiq.domain.revenue_plan import RevenuePlan, verify_revenue_evidence
        plan_payload = result['query_plan']
        if not isinstance(plan_payload, dict) or plan_payload.get('metric') != 'net_revenue_vnd':
            raise GraphResultError('Revenue query plan is malformed')
        try:
            plan = RevenuePlan(**{key: value for key, value in plan_payload.items()
                                  if key != 'metric'})
            if plan.period != result.get('period'):
                raise GraphResultError('Revenue period differs from its query plan')
            verify_revenue_evidence(plan, result.get('records', []))
        except (TypeError, ValueError) as exc:
            raise GraphResultError('Revenue result violates its query plan') from exc
    handoff = result.get('handoff')
    if handoff is not None:
        if (not isinstance(handoff, dict) or
                handoff.get('from') != 'sales_agent' or
                handoff.get('to') != 'inventory_agent' or
                agent != 'inventory_agent'):
            raise GraphResultError('Graph result has an invalid handoff')
    return result


def run(q: str, *, history: list[dict] | None = None, active_agent: str = '',
        memory: dict | None = None, verified_case_context: dict | None = None) -> dict:
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
        'customer_memory': memory if memory and memory.get('consent') else {},
        'verified_case_context': verified_case_context,
        'uc01_followup_kind': None,
        'fiction_product': None, 'fiction_warehouse': None,
        # Prevent the previous checkpoint's evidence from becoming this
        # request's answer if the subsequent execution fails or switches topic.
        'disposition': None, 'evidence_refs': [], 'findings': [],
        'source': {}, 'temporal': {}, 'capability_plan': {},
        'reason_codes': [], 'limitations': [], 'approval_status': None,
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
    payload = {'question': q, 'intent': result['intent'],
            'mode': ('LangGraph + Fiction verified SQL' if result['intent'] == 'backorder'
                     else 'LangGraph Multi-Agent + SQL / Chroma RAG'),
            'as_of': (result.get('temporal', {}).get('evidence_cutoff')
                      if result['intent'] == 'backorder' else result.get('period', month())),
            'answer': result['answer'],
            'records': result.get('records', []), 'contexts': result.get('contexts', []),
            'active_agent': result.get('active_agent', ''),
            'handoff': result.get('handoff'),
            'subagents': result.get('subagents', []),
            'skill': result.get('skill', ''),
            'route_fallback': result.get('route_fallback', False),
            'query_plan': result.get('query_plan')}
    if result['intent'] == 'backorder':
        payload.update({key: result[key] for key in
                        ('disposition', 'evidence_refs', 'findings', 'limitations',
                         'approval_status', 'reason_codes', 'source', 'capability_plan', 'temporal')})
    elif result['intent'] == 'fiction_stock':
        payload.update({key: result[key] for key in
                        ('evidence_refs', 'limitations', 'source', 'temporal')})
    if result['intent'] == 'fiction_stock':
        payload['mode'] = 'LangGraph + Fiction MCP stdio (undated stock)'
        payload['as_of'] = None  # release business date is not a stock observation timestamp
    if result['intent'] == 'backorder' and result.get('uc01_followup_kind') == 'order_details':
        payload['mode'] = 'LangGraph + Fiction SQL + real Order MCP stdio'
    return payload
