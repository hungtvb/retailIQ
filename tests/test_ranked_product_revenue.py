"""End-to-end acceptance of product-ranked revenue without store-total leakage."""
from scripts.audit_queries import run_audit


def test_ranked_sku_revenue_by_period_vietnamese_and_english():
    report = run_audit(mode='offline', ids={'SALES-05', 'SALES-06', 'SALES-07'})
    failures = [(r['id'], r['status'], r.get('observed')) for r in report['results']
                if r['status'] != 'PASS']
    assert not failures, failures
    assert report['summary'] == {'pass': 3, 'fail': 0, 'error': 0}


def test_ambiguous_group_revenue_never_falls_back_to_store_total():
    from retailiq.queries import do, intent, ranked_revenue_sku_rank
    question = 'Doanh thu tháng 10 của top 5 sellers là bao nhiêu?'
    assert intent(question) == 'revenue'
    assert ranked_revenue_sku_rank(question) is None
    result = do(question, 'revenue')
    assert result['records'] == []
    assert 'specify' in result['answer'].casefold()


def test_product_ranked_revenue_uses_exact_month_not_current_month():
    from retailiq.queries import ranked_revenue_sku_rank
    assert ranked_revenue_sku_rank('Doanh thu tháng 10 của top 1 seller?') == 1
    assert ranked_revenue_sku_rank('Revenue of the top seller in September 2026?') == 1
    assert ranked_revenue_sku_rank('Revenue of the top 3 sellers?') is None
    assert ranked_revenue_sku_rank('Revenue of the top 5 best sellers?') is None
