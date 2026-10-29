"""Audit-harness regressions: test the checker, not just existing business paths."""
from datetime import date

from scripts.audit_queries import CASES, Oracle, assess, run_audit
from scripts.seed import seed


def test_audit_oracle_uses_independent_sql(tmp_path):
    database = tmp_path / 'retail.db'
    seed(database, write_support_files=False, reference_date=date(2026, 10, 28))
    oracle = Oracle(database)
    assert oracle.priced(descending=True)['sku'] == 'EL-001'
    assert oracle.priced(descending=False)['sku'] == 'EL-004'
    assert len(oracle.top('2026-10', 5)) == 5
    assert oracle.revenue('2026-10') > oracle.revenue('2026-09') >= 0


def test_audit_detects_wrong_price_and_incomplete_multi_sku_stock(tmp_path):
    database = tmp_path / 'retail.db'
    seed(database, write_support_files=False, reference_date=date(2026, 10, 28))
    oracle = Oracle(database)
    cases = {case.id: case for case in CASES}
    valid, _, _ = assess(cases['CAT-01'], {
        'intent': 'product', 'answer': 'AlphaBook Pro 14 costs 1 VND',
        'records': [{'sku': 'EL-001', 'name': 'AlphaBook Pro 14', 'price_vnd': 1}]}, oracle)
    assert not valid
    leader = oracle.top('2026-10', 1)[0]['sku']
    valid, _, _ = assess(cases['CROSS-01'], {
        'intent': 'stock', 'answer': 'Only top one product is in stock',
        'records': [{'sku': leader, 'available': oracle.available(leader)}]}, oracle)
    assert not valid


def test_audit_accepts_correct_multi_sku_stock(tmp_path):
    database = tmp_path / 'retail.db'
    seed(database, write_support_files=False, reference_date=date(2026, 10, 28))
    oracle = Oracle(database)
    cases = {case.id: case for case in CASES}
    records = [{'sku': product['sku'], 'available': oracle.available(product['sku'])}
               for product in oracle.top('2026-10')]
    valid, _, _ = assess(cases['CROSS-01'], {
        'intent': 'stock', 'answer': 'Stock for five products', 'records': records}, oracle)
    assert valid


def test_offline_audit_smoke_calls_real_api_and_restores_environment(monkeypatch):
    keys = {'CAT-01', 'SALES-01', 'STOCK-01'}
    monkeypatch.setenv('RETAILIQ_AS_OF', '2026-03-01')
    report = run_audit(mode='offline', ids=keys)
    assert report['cases'] == len(keys)
    assert {item['id'] for item in report['results']} == keys
    assert all(item['status'] in {'PASS', 'FAIL', 'ERROR'} for item in report['results'])
    assert sum(report['summary'].values()) == len(keys)
    assert all('hypothesis' in item and 'suspected_layer' in item for item in report['results'])
    import os
    assert os.environ['RETAILIQ_AS_OF'] == '2026-03-01'
