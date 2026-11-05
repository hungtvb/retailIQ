"""Answer integrity: fail-closed period/scope and honest conversational labels.

Offline only: a temp seeded database, no provider calls and no vector store.
"""
from __future__ import annotations

from datetime import date
import os
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from retailiq.domain.analytics import requested_month
from retailiq.queries import do, intent
from retailiq.orchestration import week1_graph as graph

REFERENCE_DATE = date(2026, 10, 28)
# October 2026 store revenue in the synthetic seed: the wrong-answer number.
STORE_TOTAL = '563,742,000'
SQL_RAG_LABEL = 'LangGraph Multi-Agent + SQL / Chroma RAG'
CONVERSATIONAL_LABEL = 'LangGraph conversational (no business evidence)'


@pytest.fixture
def seeded(tmp_path):
    """Mirrors scripts/audit_queries.run_audit: isolated DB, fixed as-of date."""
    from scripts.seed import seed

    database = tmp_path / 'retailiq.sqlite3'
    seed(db_path=database, write_support_files=False, reference_date=REFERENCE_DATE)
    environment = {
        'RETAILIQ_DATA_DB': str(database),
        'RETAILIQ_AS_OF': REFERENCE_DATE.isoformat(),
        'RETAILIQ_LOG_FILE': str(tmp_path / 'events.jsonl'),
    }
    with patch.dict(os.environ, environment):
        yield database


def test_modal_may_is_not_a_month(seeded):
    assert requested_month('What revenue may we expect in October 2026?') == '2026-10'


@pytest.mark.parametrize('question', [
    'What was our revenue in previous quarter?',
    'What was our revenue in Q3 2026?',
    'Doanh thu quý 3 năm 2026 là bao nhiêu?',
    'Doanh thu tháng vừa rồi là bao nhiêu?',
])
def test_unparsed_period_clarifies(seeded, question):
    result = do(question, 'revenue')
    assert result['query_plan']['scope'] == 'clarify', result['query_plan']
    assert result['records'] == []
    assert STORE_TOTAL not in result['answer']


def test_unknown_sku_scope_clarifies(seeded):
    result = do('Doanh thu của SKU EL-999 trong tháng 10?', 'revenue')
    assert result['query_plan']['scope'] == 'clarify', result['query_plan']
    assert result['records'] == []
    assert STORE_TOTAL not in result['answer']


def test_partial_product_name_scope_clarifies(seeded):
    result = do('Revenue for AlphaBook in October 2026?', 'revenue')
    assert result['query_plan']['scope'] == 'clarify', result['query_plan']
    assert result['records'] == []
    assert STORE_TOTAL not in result['answer']


@pytest.mark.parametrize('question', [
    'Doanh thu tháng 10 tại Đà Nẵng?',
    'Doanh thu tháng 10 tại Hà Nội?',
])
def test_location_scope_clarifies(seeded, question):
    result = do(question, 'revenue')
    assert result['query_plan']['scope'] == 'clarify', result['query_plan']
    assert result['records'] == []
    assert STORE_TOTAL not in result['answer']


def test_plain_store_revenue_still_answered(seeded):
    result = do('What is our revenue in October 2026?', 'revenue')
    assert result['query_plan']['scope'] == 'store', result['query_plan']
    assert result['period'] == '2026-10'
    assert STORE_TOTAL in result['answer']


def test_data_question_routing():
    assert intent('What were our sales last month?') == 'revenue'
    assert intent('Top 3 sellers') == 'top'
    assert intent('How many orders did we ship in October?') == 'revenue'
    assert intent('Doanh so thang 10') == 'revenue'


def _fake_chat_model():
    """Router stub plus a free-form answer that invents a sales number."""

    class Router:
        def invoke(self, messages):
            return SimpleNamespace(intent=graph.classify(messages[-1][1]))

    class FakeModel:
        def with_structured_output(self, schema):
            return Router()

        def invoke(self, messages):
            question = messages[-1][1]
            content = ('I can help with inventory, revenue and product questions.'
                       if 'help' in question else 'Sales were 999')
            return SimpleNamespace(content=content)

    return FakeModel()


def test_general_answer_is_labelled_unverified(seeded, monkeypatch):
    pytest.importorskip('langgraph')
    monkeypatch.setattr(graph, 'chat_model', _fake_chat_model)

    # A plainly business question must never surface an ungrounded number under
    # the verified SQL/RAG label: either real evidence backs the label or the
    # answer is conversational and unverified.
    sales = graph.run('What were our sales last month?')
    assert 'Sales were 999' not in sales['answer']
    assert sales['mode'] != SQL_RAG_LABEL or bool(sales['records'] or sales['contexts'])

    general = graph.run('What can you help me with?')
    assert general['mode'] == CONVERSATIONAL_LABEL
    assert 'No verified business data used' in general['limitations']
    assert general['records'] == [] and general['contexts'] == []
