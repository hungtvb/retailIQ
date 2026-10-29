from types import SimpleNamespace

from retailiq.orchestration import week1_graph as graph
from retailiq import assistant


def test_general_chat_routes_to_retailiq_without_product_retrieval(monkeypatch):
    assert graph.classify('Xin chào, bạn có thể giúp gì?') == 'general'
    monkeypatch.setattr(graph, 'chat_model', lambda: SimpleNamespace(
        invoke=lambda messages: SimpleNamespace(content='Xin chào!')))
    command = graph.retailiq({'question': 'Xin chào, bạn có thể giúp gì?'})
    assert command.update['answer'] == 'Xin chào!'
    assert command.update['contexts'] == []


def test_retailiq_reply_uses_verified_rows_in_question_language():
    state = {'question': 'Doanh thu tháng này là bao nhiêu?', 'intent': 'revenue',
             'answer': 'English specialist draft', 'records': [
                 {'channel': 'Online', 'net_revenue_vnd': 100},
                 {'channel': 'Store', 'net_revenue_vnd': 200}]}
    answer = graph.retailiq_reply(state)['answer']
    assert '300 VND' in answer
    assert 'English specialist draft' not in answer
    assert graph.retailiq_reply({**state, 'question': 'What is revenue?'})['answer'] == 'English specialist draft'


def test_newest_uses_catalog_date_and_singular_top_uses_one_row(tmp_path, monkeypatch):
    from datetime import date
    from scripts.seed import seed
    from retailiq.domain.analytics import newest_products

    db = tmp_path / 'retailiq.sqlite3'
    seed(db, write_support_files=False, reference_date=date(2026, 10, 28))
    monkeypatch.setenv('RETAILIQ_DATA_DB', str(db))
    monkeypatch.setenv('RETAILIQ_AS_OF', '2026-10-28')
    assert graph.classify('Sản phẩm mới nhất là gì?') == 'latest'
    newest = newest_products()
    assert newest[0]['sku'] == 'EL-010'
    assert newest[0]['catalog_added_at'] == '2026-10-28'
    latest_answer = graph.retailiq_reply({'question': 'Sản phẩm mới nhất là gì?', 'intent': 'latest',
                                          'records': newest, 'answer': ''})['answer']
    assert 'EL-010' in latest_answer and 'ngày ra mắt thị trường' in latest_answer
    assert len(assistant.do('Sản phẩm mới nhất là gì?', 'latest')['records']) == 1
    assert len(assistant.do('Sản phẩm bán chạy nhất là gì?', 'top')['records']) == 1
    assert len(assistant.do('Top 5 sản phẩm bán chạy', 'top')['records']) == 5
    history = [{'role': 'user', 'content': 'Sản phẩm mới nhất là gì?'},
               {'role': 'assistant', 'content': 'Untrusted model text'}]
    assert graph.followup_intent('Giá của nó bao nhiêu?', history) == 'product'
    assert graph.resolve_followup('Giá của nó bao nhiêu?', history, 'product').endswith('EL-010')
    assert graph.followup_intent('Nó còn hàng không?', history) == 'stock'
    assert graph.resolve_followup('Nó còn hàng không?', history, 'stock').endswith('EL-010')
    assert graph.followup_intent('Bạn có thể kể chuyện không?', history) == 'general'
    chained = history + [{'role': 'user', 'content': 'Giá của nó bao nhiêu?'}]
    assert graph.followup_intent('Nó dùng cổng gì?', chained) == 'product'
    assert graph.resolve_followup('Nó dùng cổng gì?', chained, 'product').endswith('EL-010')
    after_stock = chained + [{'role': 'user', 'content': 'Nó còn hàng không?'}]
    assert graph.followup_intent('Nó dùng cổng gì?', after_stock) == 'product'
    interrupted = chained + [{'role': 'user', 'content': 'Hôm nay trời đẹp quá'}]
    assert graph.followup_intent('Nó dùng cổng gì?', interrupted) == 'general'
    price = assistant.offline('Giá của nó bao nhiêu?', history=history)
    assert price['intent'] == 'product'
    assert price['records'][0]['sku'] == 'EL-010'
    assert '8,990,000 VND' in price['answer']


def test_requested_sales_month_controls_query_answer_and_metadata(tmp_path, monkeypatch):
    from datetime import date
    from scripts.seed import seed
    from retailiq.domain.analytics import requested_month, revenue

    db = tmp_path / 'retailiq.sqlite3'
    seed(db, write_support_files=False, reference_date=date(2026, 10, 28))
    monkeypatch.setenv('RETAILIQ_DATA_DB', str(db))
    monkeypatch.setenv('RETAILIQ_AS_OF', '2026-10-28')
    assert requested_month('Có số liệu doanh thu tháng 9 không?') == '2026-09'
    assert requested_month('Doanh thu tháng 9 năm 2025?') == '2025-09'
    assert requested_month('Doanh thu tháng trước?') == '2026-09'
    assert graph.followup_intent('Tháng 9 thì sao?',
                                 [{'role': 'user', 'content': 'Doanh thu tháng này?'}]) == 'revenue'
    assert revenue('2026-09') != revenue('2026-10')
    result = assistant.do('Có số liệu doanh thu tháng 9 không?', 'revenue')
    assert result['period'] == '2026-09'
    assert '2026-09' in result['answer']
    localized = graph.retailiq_reply({'question': 'Có số liệu doanh thu tháng 9 không?',
                                       'intent': 'revenue', **result})['answer']
    assert '2026-09' in localized
    assert '2026-10' not in localized
