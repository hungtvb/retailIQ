"""Bounded Fiction business journey for the existing /ask and /ask/stream API.

This is a deterministic, source-grounded vertical slice, NOT an LLM or LangGraph
run. It never uses retired EL-### tools or mixes generated review text with
observed customer feedback.
"""
from __future__ import annotations

from datetime import date
import hashlib
import json
import os
from pathlib import Path
import re

from retailiq.domain import fiction
from retailiq.observability import log_event

_MONTH = re.compile(r'(?:tháng\s*(1[0-2]|0?[1-9])\s*(?:/|năm\s*|[- ])\s*(20\d{2})|\b(20\d{2})[-/](1[0-2]|0?[1-9])\b)', re.I)
_RANK = re.compile(r'(?:sản phẩm\s*(?:số|thứ)\s*|(?:đứng|xếp)\s*thứ\s*|(?:rank|#)\s*)(\d{1,3})\b', re.I)
_TOP = re.compile(r'(?:\btop\s*(\d{1,3})\b|top\s*sellers?|bán chạy)', re.I)
_UUID = re.compile(r'(?<![\w-])([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})(?![\w-])', re.I)
_STOCK = ('tồn kho', 'còn hàng', 'còn bao nhiêu', 'stock', 'inventory', 'available')
_RETURN = ('trả hàng', 'hoàn trả', 'đổi trả', 'return', 'refund', 'phàn nàn', 'đánh giá', 'review', 'khiếu nại')
_KNOWLEDGE = ('thông số', 'bảo hành', 'tương thích', 'tài liệu', 'review', 'đánh giá', 'phàn nàn', 'manual', 'warranty', 'spec')


def _hash(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def _month(q: str) -> str | None:
    m = _MONTH.search(q)
    if not m:
        return None
    return f'{int(m.group(2) or m.group(3)):04d}-{int(m.group(1) or m.group(4)):02d}'


def _rank(q: str) -> int | None:
    m = _RANK.search(q)
    return int(m.group(1)) if m else None


def _top_count(q: str) -> int:
    m = _TOP.search(q)
    return int(m.group(1)) if m and m.group(1) else 5


def _refs(history: list[dict]) -> tuple[str | None, int | None, int | None]:
    """Only user-authored ranking questions can establish a historical scope.

    A subsequent user question with an explicit rank chooses that product; no
    product IDs are inferred from assistant-generated prose.
    """
    top_period = None
    top_count = None
    rank = None
    for msg in history:
        if msg.get('role') != 'user' or not isinstance(msg.get('content'), str):
            continue
        text = msg['content']
        if _TOP.search(text) and _month(text):
            top_period, top_count, rank = _month(text), _top_count(text), None
        elif top_period is not None and (selected_rank := _rank(text)) is not None:
            rank = selected_rank
        elif top_period is not None and _month(text) is not None:
            # New unrelated explicitly dated question invalidates inherited scope.
            top_period, top_count, rank = None, None, None
    return top_period, top_count, rank


def _coverage(db: Path, period: str) -> bool:
    first = date.fromisoformat(period + '-01')
    with fiction.connect(db) as conn:
        row = conn.execute('SELECT MIN(order_date), MAX(order_date) FROM orders').fetchone()
    if row[0] is None:
        return False
    last = date.fromisoformat(row[1][:10])
    begin = date.fromisoformat(row[0][:10])
    # Require a complete calendar month to avoid presenting a partial dataset
    # month as complete. The published source ends on 2024-04-30.
    if first < begin.replace(day=1) or first > last.replace(day=1):
        return False
    return True


def _documents(source: Path, product_id: str) -> list[dict]:
    """Exact-ID, provenance-constrained document lookup; no vector/RAG claim."""
    root_env = os.getenv('RETAILIQ_FICTION_CORPUS')
    if not root_env:
        return []
    root = Path(root_env).expanduser().resolve()
    manifest_file = root / '.generation_manifest'
    records_file = root / 'records.jsonl'
    if not manifest_file.is_file() or not records_file.is_file():
        return []
    manifest = json.loads(manifest_file.read_text(encoding='utf8'))
    if manifest.get('source_sha256') != _hash(source):
        raise fiction.FictionDataError('Fiction corpus was generated from another source snapshot')
    result = []
    for line in records_file.read_text(encoding='utf8').splitlines():
        record = json.loads(line)
        if record.get('product_id') != product_id or record.get('kind') not in ('product_catalog','customer_review','support_ticket'):
            continue
        relative = record['path']
        path = (root / relative).resolve()
        if not path.is_relative_to(root) or not path.is_file():
            raise fiction.FictionDataError('Corpus reference is missing or unsafe')
        text = path.read_text(encoding='utf8')
        if f'Product ID: {product_id}\n' not in text:
            raise fiction.FictionDataError('Corpus Product ID mismatch')
        result.append({'source': f'fiction-corpus/{relative}', 'product_id': product_id,
                       'kind': record['kind'], 'synthetic': bool(record['is_synthetic_text']),
                       'text': text[:1800]})
    return result[:20]


def _response(q: str, intent: str, answer: str, *, rows: list | None = None,
              contexts: list | None = None, period: str | None = None,
              status: str = 'OK', selected_product_id: str | None = None) -> dict:
    return {'question': q, 'intent': intent, 'answer': answer, 'records': rows or [],
            'contexts': contexts or [], 'mode': 'FICTION_DETERMINISTIC_SQL_NOT_LANGGRAPH',
            'active_agent': 'fiction_data_workflow', 'skill': 'fiction_data_evidence',
            'period': period, 'as_of': period or 'historical_snapshot',
            'data_status': status, 'selected_product_id': selected_product_id,
            'source': 'Fiction Retail SQLite; historical synthetic retailer'}


def _inventory(source: Path, pid: str) -> tuple[str, list]:
    stocks = fiction.stock(source, pid)
    if not stocks:
        return 'Không có bản ghi tồn kho cho sản phẩm này.', []
    available = sum(i['available'] for i in stocks)
    info = '; '.join(f"{i['warehouse']}: {i['available']:,} (on-hand {i['quantity_on_hand']:,}, reserved {i['reserved_quantity']:,})" for i in stocks)
    return (f'Tồn khả dụng trong snapshot Fiction: {available:,} đơn vị trên {len(stocks)} kho. '
            f'{info}. Không có timestamp đồng bộ, nên không coi đây là tồn kho hiện tại hoặc tồn kho tại tháng được hỏi.'), stocks


def _returns(source: Path, pid: str, period: str) -> tuple[str, list]:
    reasons = fiction.return_reasons(source, period, product_id=pid)
    total = sum(x['return_events'] for x in reasons)
    details = ', '.join(f"{x['reason_code']}: {x['return_events']}" for x in reasons)
    return (f'Có {total} sự kiện trả hàng ghi nhận theo return_date tháng {period}' +
            (f' ({details}). ' if details else '. ') +
            'Đây không phải tỷ lệ trả hàng của cohort bán trong tháng; không có bằng chứng về cảm nhận khách hàng.'), reasons


def ask(question: str, *, history: list[dict] | None = None) -> dict:
    """Run one trusted, limited business step on the selected Fiction snapshot."""
    source_value = os.getenv('RETAILIQ_FICTION_DB')
    if not source_value:
        raise FileNotFoundError('Configure RETAILIQ_FICTION_DB; legacy dataset fallback is forbidden')
    source = Path(source_value).expanduser().resolve()
    if not source.is_file():
        raise FileNotFoundError('Configured Fiction snapshot not found')
    history = history or []
    q = question.casefold()
    current_period = _month(question)
    prior_period, prior_count, prior_rank = _refs(history)
    is_top = bool(_TOP.search(question))
    wants_stock = any(t in q for t in _STOCK)
    wants_returns = any(t in q for t in _RETURN)
    wants_knowledge = any(t in q for t in _KNOWLEDGE)
    explicit_pid = _UUID.search(question)
    period = current_period or prior_period
    log_event('fiction.workflow_started', intent='cross_source' if is_top and wants_stock else 'lookup', execution_mode='fiction_deterministic')

    if is_top and current_period:
        if not _coverage(source, current_period):
            return _response(question,'top','Không có dữ liệu giao dịch bao phủ kỳ này trong Fiction (chỉ có lịch sử đến 04/2024). Không được diễn giải là doanh số bằng 0.',period=current_period,status='DATA_NOT_AVAILABLE')
        limit = _top_count(question)
        if not 1 <= limit <= 20:
            return _response(question,'top','Chỉ hỗ trợ top 1–20 sản phẩm mỗi lần.',period=period,status='CLARIFY')
        ranked = fiction.top_sellers(source, current_period, limit=limit)
        log_event('fiction.tool_completed', tool='top_sellers', agent='sales_agent', execution_mode='fiction_deterministic')
        if not ranked:
            return _response(question,'top',f'Không có giao dịch delivered trong kỳ {period}.',period=period,status='NO_ACTIVITY')
        lines = [f"{i}. {p['name']} (Product ID: {p['product_id']}): {p['delivered_units']} đơn vị" for i,p in enumerate(ranked,1)]
        contexts = [{'source':'fiction-retail.db#orders+order_items+products', 'text':'Delivered-order units by order_date', 'period':period}]
        evidence_rows = [dict(p) for p in ranked]
        if wants_stock or wants_returns or wants_knowledge:
            for p, record in zip(ranked, evidence_rows):
                pid = p['product_id']
                if wants_stock:
                    info, stocks = _inventory(source, pid)
                    record['available_snapshot'] = sum(r['available'] for r in stocks)
                    record['stock_freshness'] = 'UNVERIFIED_HISTORICAL_SNAPSHOT'
                    lines.append(f"Tồn kho {pid}: {info}")
                    contexts.append({'source':f'fiction-retail.db#inventory/{pid}', 'text':'Current-in-file snapshot, actual time unknown', 'product_id':pid})
                    log_event('fiction.tool_completed', tool='inventory', agent='inventory_agent', execution_mode='fiction_deterministic')
                if wants_returns:
                    info, reasons = _returns(source,pid,period)
                    record['return_events_by_return_date'] = sum(r['return_events'] for r in reasons)
                    lines.append(f"Trả hàng {pid}: {info}")
                    contexts.append({'source':f'fiction-retail.db#returns/{pid}/{period}', 'text':'Return reasons by return_date, not sales cohort', 'product_id':pid})
                    log_event('fiction.tool_completed', tool='returns', agent='returns_agent', execution_mode='fiction_deterministic')
                if wants_knowledge:
                    docs = _documents(source, pid)
                    record['corpus_catalog_documents'] = sum(x['kind']=='product_catalog' for x in docs)
                    record['synthetic_reviews'] = sum(x['kind']=='customer_review' for x in docs)
                    contexts.extend(x for x in docs if x['kind']=='product_catalog' or x['kind']=='customer_review')
                    lines.append(f"Tài liệu {pid}: {record['corpus_catalog_documents']} catalog, {record['synthetic_reviews']} review mô phỏng (không phải feedback thật).")
                    log_event('fiction.tool_completed', tool='corpus_exact_id', agent='product_agent', execution_mode='fiction_deterministic')
            lines.append('Không thể suy ra tỷ lệ trả hàng theo cohort hoặc đánh giá khách hàng thực từ các số liệu này.')
        return _response(question,'cross_source' if wants_stock or wants_returns or wants_knowledge else 'top',
                         f'Top {limit} sản phẩm theo số lượng giao tháng {period}:\n'+'\n'.join(lines),
                         rows=evidence_rows,contexts=contexts,period=period)

    selected_pid = explicit_pid.group(1).lower() if explicit_pid else None
    if not selected_pid:
        rank = _rank(question) or prior_rank
        if rank and prior_period and prior_count and 1 <= rank <= prior_count:
            ranked = fiction.top_sellers(source, prior_period,limit=prior_count)
            if rank <= len(ranked):
                selected_pid = ranked[rank-1]['product_id']
        elif rank:
            return _response(question,'clarification','Không thể xác định sản phẩm theo thứ hạng vì thiếu danh sách top và kỳ trước đó, hoặc thứ hạng ngoài phạm vi.',status='CLARIFY')
    if selected_pid:
        p = fiction.product(source,selected_pid)
        if p is None:
            return _response(question,'product','Không tìm thấy Product ID trong Fiction.',status='NOT_FOUND')
        lines = [f"{p['name']} (Product ID: {selected_pid}); brand: {p['brand']}, category: {p['category']}, giá catalog: {p['price']} USD."]
        contexts = [{'source':f'fiction-retail.db#products/{selected_pid}','text':'Catalog facts','product_id':selected_pid}]
        records = [p]
        if wants_stock:
            info, rows = _inventory(source,selected_pid)
            lines.append(info)
            records.extend(rows)
            contexts.append({'source':f'fiction-retail.db#inventory/{selected_pid}','text':'Warehouse stock snapshot','product_id':selected_pid})
        if wants_returns:
            if not period:
                return _response(question,'clarification','Cần chỉ rõ tháng/năm hoặc hỏi tiếp từ danh sách top có kỳ xác định để kiểm tra trả hàng.',status='CLARIFY')
            if not _coverage(source,period):
                return _response(question,'returns','Kỳ được hỏi nằm ngoài thời gian dữ liệu Fiction; không thể kết luận không có trả hàng.',period=period,status='DATA_NOT_AVAILABLE')
            info, rows = _returns(source,selected_pid,period)
            lines.append(info)
            records.extend(rows)
            contexts.append({'source':f'fiction-retail.db#returns/{selected_pid}/{period}','text':'Return reasons by return_date','product_id':selected_pid})
        if wants_knowledge:
            docs = _documents(source,selected_pid)
            contexts.extend(docs)
            catalog = [x for x in docs if x['kind']=='product_catalog']
            reviews = [x for x in docs if x['kind']=='customer_review']
            lines.append(f'Tài liệu catalog có trong corpus: {len(catalog)}; review mô phỏng: {len(reviews)}. Không có review khách hàng thực trong Fiction.')
            if any(t in q for t in ('warranty','bảo hành','spec','thông số','tương thích')):
                lines.append('Không có thông số kỹ thuật, chính sách bảo hành hay bằng chứng tương thích trong nguồn. Không được suy đoán.')
        return _response(question,'product_evidence', '\n'.join(lines),rows=records,contexts=contexts,
                         period=period, selected_product_id=selected_pid)

    if wants_returns or wants_stock or wants_knowledge or is_top:
        return _response(question,'clarification','Hãy chỉ rõ Product ID hoặc hỏi “top 5 sản phẩm bán chạy tháng 4/2024”, sau đó chọn “sản phẩm số 1”.',status='CLARIFY')
    if any(t in q for t in ('doanh thu','revenue','sales')):
        if not current_period:
            return _response(question,'clarification','Vui lòng nêu tháng/năm; dữ liệu Fiction chỉ là lịch sử.',status='CLARIFY')
        if not _coverage(source,current_period):
            return _response(question,'revenue','Ngoài phạm vi lịch sử Fiction. Chưa có dữ liệu, không phải doanh thu bằng 0.',period=current_period,status='DATA_NOT_AVAILABLE')
        data = fiction.delivered_merchandise_value(source,current_period)
        return _response(question,'revenue',f"Giá trị hàng trong đơn delivered tháng {current_period}: {data['amount_usd']} USD, sau discount, trước returns/tax/shipping; KHÔNG phải net revenue.",rows=[data],period=current_period)
    return _response(question,'general','Fiction hỗ trợ tra cứu lịch sử Sales, Inventory, Returns theo Product ID/kỳ. Hãy đưa câu hỏi có tháng/năm cụ thể.',status='CLARIFY')