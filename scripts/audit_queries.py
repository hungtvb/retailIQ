"""Observational RetailIQ query audit: baseline hypotheses vs actual /ask output.

Does not change product logic or overwrite the user's databases.
Default: python -m scripts.audit_queries
Full: python -m scripts.audit_queries --mode full --ids CAT-01,CROSS-01 --confirm-live
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from contextlib import closing
from dataclasses import dataclass
from datetime import date
import json
import os
from pathlib import Path
import sqlite3
import tempfile

REFERENCE_DATE = date(2026, 10, 28)


@dataclass(frozen=True)
class Case:
    id: str
    group: str
    questions: tuple[str, ...]
    check: str
    prediction: str
    suspected_layer: str
    description: str
    period: str = '2026-10'
    n: int = 0
    sku: str = ''
    category: str = ''


# Predictions are from reading the current source, NOT recorded test results.
CASES = (
    Case('CAT-01','catalog',('Sản phẩm nào mắc nhất?',),'price_max','LIKELY_FAIL','router/catalog_sql','Most expensive (VI)'),
    Case('CAT-02','catalog',('Sản phẩm nào đắt nhất?',),'price_max','LIKELY_FAIL','router/catalog_sql','Most expensive (VI alternative)'),
    Case('CAT-03','catalog',('Sản phẩm nào rẻ nhất?',),'price_min','LIKELY_FAIL','router/catalog_sql','Cheapest (VI)'),
    Case('CAT-04','catalog',('What is the cheapest product?',),'price_min','LIKELY_FAIL','router/catalog_sql','Cheapest (EN)'),
    Case('CAT-05','catalog',('Which product is the most expensive?',),'price_max','LIKELY_FAIL','router/catalog_sql','Most expensive (EN)'),
    Case('CAT-06','catalog',('Giá của AlphaBook Pro 14 là bao nhiêu?',),'price_named','LIKELY_PASS','catalog_lookup/response','Price of known product',sku='EL-001'),
    Case('CAT-07','catalog',('Phụ kiện nào rẻ nhất?',),'price_min','LIKELY_FAIL','category_filter/catalog_sql','Cheapest accessory',category='Accessory'),
    Case('SALES-01','sales',('Doanh thu tháng 10 năm 2026 là bao nhiêu?',),'revenue','LIKELY_PASS','sales_sql/period','October completed-order revenue'),
    Case('SALES-02','sales',('Doanh thu tháng 9 năm 2026?',),'revenue','LIKELY_PASS','sales_sql/period','September completed-order revenue',period='2026-09'),
    Case('SALES-03','sales',('Top 5 sản phẩm bán chạy tháng 10 năm 2026?',),'top','LIKELY_PASS','sales_sql/ranking','Top five sold units',n=5),
    Case('SALES-04','sales',('Top 3 sản phẩm bán chạy tháng 10 năm 2026?',),'top','LIKELY_FAIL','query_limit/response','Exactly top three',n=3),
    Case('STOCK-01','stock',('Tồn kho AlphaBook Pro 14 hiện có bao nhiêu?',),'stock_sku','LIKELY_PASS','inventory_sql','Single known SKU',sku='EL-001'),
    Case('STOCK-02','stock',('Sản phẩm không xác định còn bao nhiêu trong kho?',),'clarify','LIKELY_PASS','stock_validation','Unknown product must not invent stock'),
    Case('CROSS-01','cross_domain',('Tồn kho của top 5 sản phẩm bán chạy tháng 10 năm 2026?',),'stock_top','LIKELY_FAIL','router/supervisor/multi_sku','Top five inventory, VI',n=5),
    Case('CROSS-02','cross_domain',('How many units are in stock for the top 5 best sellers?',),'stock_top','LIKELY_FAIL','router/stock_single_sku','Top five inventory, EN',n=5),
    Case('CTX-01','context',('Which products are top sellers?','How many units of the top seller are in stock?'),'stock_top_handoff','LIKELY_PASS','history/handoff','Sales to Inventory follow-up',n=1),
    Case('CTX-02','context',('Doanh thu tháng 10 năm 2026?','Còn tháng trước?'),'revenue','LIKELY_PASS','history/period','Prior-month revenue follow-up',period='2026-09'),
    Case('CTX-03','context',('Top 5 sản phẩm bán chạy tháng 9 năm 2026?','Tồn kho của các sản phẩm đó?'),'stock_top','LIKELY_FAIL','history/multi_sku/period','Pronoun = five September SKUs',period='2026-09',n=5),
    Case('CTX-04','context',('Top 5 sản phẩm bán chạy tháng 9 năm 2026?','Tồn kho của sản phẩm đứng thứ 2?'),'stock_rank','LIKELY_FAIL','history/rank/period','Second-ranked SKU from September',period='2026-09',n=2),
    Case('RAG-01','product',('Thông số USB-C GaN Charger 65W như thế nào?',),'product_sources','LIKELY_PASS','retrieval/grounding','Document-backed product answer'),
)


class Oracle:
    """Independent reference SQL; does not use application router or query tools."""
    def __init__(self, db: Path):
        self.db = db

    def query(self, sql: str, args: tuple = ()) -> list[dict]:
        with closing(sqlite3.connect(self.db.resolve().as_uri()+'?mode=ro', uri=True)) as conn:
            conn.row_factory = sqlite3.Row
            return [dict(row) for row in conn.execute(sql, args)]

    def priced(self, descending: bool, category: str = '') -> dict:
        direction = 'DESC' if descending else 'ASC'
        if category:
            return self.query('SELECT sku,name,price_vnd FROM products WHERE category=? '
                              f'ORDER BY price_vnd {direction},sku LIMIT 1', (category,))[0]
        return self.query(f'SELECT sku,name,price_vnd FROM products ORDER BY price_vnd {direction},sku LIMIT 1')[0]

    def product(self, sku: str) -> dict:
        return self.query('SELECT sku,name,price_vnd FROM products WHERE sku=?', (sku,))[0]

    @staticmethod
    def bounds(period: str) -> tuple[str, str]:
        year, month = map(int, period.split('-'))
        return period+'-01', f'{year+1}-01-01' if month == 12 else f'{year}-{month+1:02d}-01'

    def top(self, period: str, n: int = 5) -> list[dict]:
        start, end = self.bounds(period)
        return self.query('''SELECT li.sku,p.name,SUM(li.quantity) AS units_sold
            FROM orders o JOIN order_lines li ON li.order_id=o.id JOIN products p ON p.sku=li.sku
            WHERE o.status='completed' AND o.ordered_at>=? AND o.ordered_at<?
            GROUP BY li.sku,p.name ORDER BY units_sold DESC,li.sku LIMIT ?''', (start,end,n))

    def revenue(self, period: str) -> int:
        start, end = self.bounds(period)
        rows = self.query('''SELECT SUM(li.quantity*li.unit_price_vnd-li.discount_vnd) AS total
            FROM orders o JOIN order_lines li ON li.order_id=o.id
            WHERE o.status='completed' AND o.ordered_at>=? AND o.ordered_at<?''', (start,end))
        return rows[0]['total'] or 0

    def available(self, sku: str) -> int:
        return self.query('SELECT COALESCE(SUM(on_hand-reserved),0) AS available FROM inventory WHERE sku=?',(sku,))[0]['available']


def has_number(answer: str, number: int) -> bool:
    return any(v in answer for v in (str(number), f'{number:,}', f'{number:,}'.replace(',','.')))


def assess(case: Case, response: dict, oracle: Oracle) -> tuple[bool,str,dict]:
    """Require correct records and answer; HTTP success alone never counts as PASS."""
    rows = response.get('records') or []
    answer = response.get('answer') or ''
    if not isinstance(rows,list) or not isinstance(answer,str):
        return False,'Malformed output',{}
    check = case.check
    if check.startswith('price_'):
        expected = oracle.product(case.sku) if check == 'price_named' else oracle.priced(
            check == 'price_max', case.category)
        matches = [r for r in rows if isinstance(r,dict) and r.get('sku') == expected['sku']
                   and r.get('price_vnd') == expected['price_vnd']]
        ok = bool(matches) and (expected['sku'] in answer or expected['name'] in answer) and has_number(answer,expected['price_vnd'])
        return ok,'Catalog price and SKU must appear in records and answer',expected
    if check == 'revenue':
        total = oracle.revenue(case.period)
        actual = sum(r['net_revenue_vnd'] for r in rows if isinstance(r,dict) and type(r.get('net_revenue_vnd')) is int)
        ok = response.get('intent') == 'revenue' and actual == total and has_number(answer,total)
        return ok,'Revenue sum, time window, and displayed answer',{'period':case.period,'net_revenue_vnd':total}
    if check == 'top':
        expected = oracle.top(case.period,case.n)
        actual = [(r.get('sku'),r.get('units_sold')) for r in rows if isinstance(r,dict)]
        ok = actual == [(r['sku'],r['units_sold']) for r in expected]
        return ok,'Rank, count and units must match SQL',{'period':case.period,'ranked':expected}
    if check == 'stock_sku':
        matches = [r for r in rows if isinstance(r,dict) and r.get('sku') == case.sku
                   and type(r.get('available')) is int]
        expected = {'sku':case.sku,'available':oracle.available(case.sku)}
        ok = bool(matches) and len(matches) == len(rows) and sum(r['available'] for r in matches) == expected['available']
        return ok,'Per-SKU available units must match SQL',expected
    if check == 'clarify':
        return not rows and bool(answer.strip()) and response.get('intent') == 'stock','No fabricated stock for unknown product',{'records':[]}
    if check in ('stock_top','stock_top_handoff','stock_rank'):
        ranked = oracle.top(case.period, 5 if check == 'stock_rank' else case.n)
        skus = [ranked[case.n-1]['sku']] if check == 'stock_rank' else [p['sku'] for p in ranked]
        expected = {sku:oracle.available(sku) for sku in skus}
        found = defaultdict(int)
        for row in rows:
            if isinstance(row,dict) and isinstance(row.get('sku'),str) and type(row.get('available')) is int:
                found[row['sku']] += row['available']
        ok = set(found) == set(expected) and dict(found) == expected
        if check == 'stock_top_handoff':
            ok = ok and response.get('active_agent') == 'inventory_agent' and bool(response.get('handoff'))
        return ok,'All selected SKUs must have correct stock; handoff if requested',{'period':case.period,'sku_available':expected}
    if check == 'product_sources':
        contexts = response.get('contexts') or []
        ok = response.get('intent') == 'product' and isinstance(contexts,list) and bool(contexts) and bool(answer.strip())
        return ok,'Document source required',{'minimum_sources':1}
    raise ValueError('Unknown check '+check)


def run_audit(mode: str = 'offline', ids: set[str] | None = None) -> dict:
    """Runs actual /ask API using isolated retail, chat and checkpoint databases."""
    from scripts.seed import seed
    with tempfile.TemporaryDirectory(prefix='retailiq-acceptance-') as directory:
        directory = Path(directory)
        database = directory/'retail.sqlite3'
        seed(db_path=database,write_support_files=False,reference_date=REFERENCE_DATE)
        os.environ.update({'RETAILIQ_MODE':mode,'RETAILIQ_AS_OF':REFERENCE_DATE.isoformat(),
                           'RETAILIQ_DATA_DB':str(database),'RETAILIQ_CHAT_DB':str(directory/'chat.sqlite3'),
                           'RETAILIQ_CHECKPOINT_DB':str(directory/'checkpoint.sqlite3')})
        from fastapi.testclient import TestClient
        from retailiq.api import app
        oracle = Oracle(database)
        results = []
        with TestClient(app) as client:
            for case in CASES:
                if ids is not None and case.id not in ids:
                    continue
                report = {'id':case.id,'group':case.group,'questions':list(case.questions),
                          'hypothesis':case.prediction,'suspected_layer':case.suspected_layer,
                          'description':case.description}
                try:
                    created = client.post('/api/sessions',json={})
                    if created.status_code != 201:
                        raise RuntimeError(f'HTTP {created.status_code} creating session')
                    sid = created.json()['id']
                    for question in case.questions:
                        raw = client.post('/ask',json={'question':question,'session_id':sid})
                        if raw.status_code != 200:
                            detail = raw.json().get('detail','request failed')
                            raise RuntimeError(f'HTTP {raw.status_code}: {str(detail)[:180]}')
                    result = raw.json()
                    ok,rule,expected = assess(case,result,oracle)
                    records = result.get('records') or []
                    report.update({'status':'PASS' if ok else 'FAIL','check':rule,
                                   'expected':expected,'observed':{
                                       'intent':result.get('intent'),'agent':result.get('active_agent'),
                                       'record_count':len(records),
                                       'skus':sorted({r.get('sku') for r in records if isinstance(r,dict)
                                                      and isinstance(r.get('sku'),str)}),
                                       'answer':str(result.get('answer',''))[:800]}})
                except Exception as error:
                    report.update({'status':'ERROR','error_type':type(error).__name__,
                                   'error':str(error)[:240] if isinstance(error,RuntimeError) else
                                   'Execution error; inspect server logs'})
                results.append(report)
        counts = Counter(r['status'] for r in results)
        return {'schema_version':1,'mode':mode,'reference_date':REFERENCE_DATE.isoformat(),
                'cases':len(results),'summary':{'pass':counts['PASS'],'fail':counts['FAIL'],
                                               'error':counts['ERROR']},
                'note':'Hypotheses are separate from observations. Full mode may incur live provider cost.',
                'results':results}


def main() -> int:
    parser = argparse.ArgumentParser(description='RetailIQ question acceptance audit')
    parser.add_argument('--mode',choices=('offline','full'),default='offline')
    parser.add_argument('--ids',help='Comma-separated case IDs')
    parser.add_argument('--confirm-live',action='store_true',help='Required before paid full-mode calls')
    parser.add_argument('--strict',action='store_true',help='Fail exit status on any FAIL or ERROR')
    parser.add_argument('--out',default='data/query_audit_report.json')
    args = parser.parse_args()
    if args.mode == 'full' and not args.confirm_live:
        parser.error('Full mode makes real provider calls: pass --confirm-live')
    ids = set(args.ids.split(',')) if args.ids else None
    unknown = ids - {case.id for case in CASES} if ids else set()
    if unknown:
        parser.error('Unknown case IDs: '+', '.join(sorted(unknown)))
    report = run_audit(mode=args.mode,ids=ids)
    output = Path(args.out)
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    summary = report['summary']
    print(f"Audit {args.mode}: {summary['pass']} PASS / {summary['fail']} FAIL / {summary['error']} ERROR")
    for row in report['results']:
        print(f"  {row['id']:9} {row['status']:5} predicted={row['hypothesis']:11} layer={row['suspected_layer']}")
    print('Report:',output.resolve())
    return int(args.strict and (summary['fail'] > 0 or summary['error'] > 0))


if __name__ == '__main__':
    raise SystemExit(main())
