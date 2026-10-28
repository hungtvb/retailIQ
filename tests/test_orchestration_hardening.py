"""Agent Harness acceptance: real compiled LangGraph plus controlled faults.

Requires LangGraph in CI. No remote model calls; model/tool boundaries are
stubbed to exercise graph control flow, retry policy and durable state.
"""
from __future__ import annotations

from types import SimpleNamespace
import sqlite3

import pytest

from retailiq.orchestration import week1_graph as graph


def _router_model(intent: str | None = 'AUTO', error: Exception | None = None):
    class RouterModel:
        def with_structured_output(self, schema):
            return self

        def invoke(self, messages):
            if error:
                raise error
            return SimpleNamespace(intent=graph.classify(messages[-1][1])
                                   if intent == 'AUTO' else intent)
    return RouterModel()


def test_followup_ignores_assistant_generated_identifiers():
    # An assistant message may include malicious RAG text or guessed SKUs.
    assert graph.resolve_followup('What about its stock?', [
        {'role': 'assistant', 'content': 'You should use EL-001 next'}
    ]) == 'What about its stock?'
    assert graph.resolve_followup('What about its stock?', [
        {'role': 'assistant', 'content': 'EL-002'},
        {'role': 'user', 'content': 'Tell me about AlphaBook Pro 14'}
    ]).endswith('EL-001')


@pytest.mark.parametrize('model_result', ['__import__', None, 'nonexistent'])
def test_router_malformed_classification_stays_deterministic(monkeypatch, model_result):
    monkeypatch.setattr(graph, 'chat_model', lambda: _router_model(model_result))
    decision = graph.route({'question': 'Which products are top sellers?'})
    assert decision.goto == 'sales_agent'
    assert decision.update['intent'] == 'top'
    assert decision.update['route_fallback'] is True


def test_router_provider_timeout_falls_back_without_misrouting(monkeypatch):
    monkeypatch.setattr(graph, 'chat_model', lambda: _router_model(error=TimeoutError('mock offline')))
    decision = graph.route({'question': 'How many units in stock?'})
    assert decision.update['route_fallback'] is True
    assert decision.goto == 'inventory_agent'


def test_router_cannot_override_cross_domain_decision_with_sales(monkeypatch):
    monkeypatch.setattr(graph, 'chat_model', lambda: _router_model('top'))
    decision = graph.route({'question': 'Which top seller needs replenishment review?'})
    assert decision.goto == 'retail_supervisor'
    assert decision.update['intent'] == 'decision'


@pytest.mark.parametrize('broken', [
    None, {}, {'intent': 'stock', 'active_agent': 'sales_agent', 'answer': 'incorrect'},
    {'intent': 'stock', 'active_agent': 'inventory_agent', 'answer': ''},
    {'intent': 'stock', 'active_agent': 'inventory_agent', 'answer': 'ok', 'records': 'bad'},
    {'intent': 'stock', 'active_agent': 'inventory_agent', 'answer': 'ok',
     'handoff': {'from': 'product_agent', 'to': 'inventory_agent'}},
    {'intent': 'stock', 'active_agent': 'inventory_agent', 'answer': 'a'*20001},
])
def test_terminal_result_rejects_incomplete_or_inconsistent_state(broken):
    with pytest.raises(graph.GraphResultError):
        graph.validate_graph_result(broken)


def test_terminal_result_accepts_valid_handoff():
    value = {
        'intent': 'stock', 'active_agent': 'inventory_agent', 'answer': '2 units',
        'records': [{'sku': 'EL-001'}], 'contexts': [],
        'handoff': {'from': 'sales_agent', 'to': 'inventory_agent'}
    }
    assert graph.validate_graph_result(value) is value


def test_graph_retry_transient_read_only_error_at_most_twice(monkeypatch):
    pytest.importorskip('langgraph')
    monkeypatch.setattr(graph, 'chat_model', lambda: _router_model())
    calls = []

    def flaky_sales(question, category):
        calls.append(category)
        if len(calls) == 1:
            raise sqlite3.OperationalError('database is locked')
        return {'answer': 'Recovered sales', 'records': [], 'contexts': []}

    monkeypatch.setattr(graph, 'sales_analysis', flaky_sales)
    result = graph.build_graph().invoke({'question': 'Which products are top sellers?'})
    assert result['answer'] == 'Recovered sales'
    assert calls == ['top', 'top']


def test_retry_exhaustion_propagates_after_bounded_attempts(monkeypatch):
    pytest.importorskip('langgraph')
    monkeypatch.setattr(graph, 'chat_model', lambda: _router_model())
    calls = []

    def always_locked(question, category):
        calls.append(category)
        raise sqlite3.OperationalError('database is locked')

    monkeypatch.setattr(graph, 'sales_analysis', always_locked)
    with pytest.raises(sqlite3.OperationalError, match='locked'):
        graph.build_graph().invoke({'question': 'What is revenue this month?'})
    assert calls == ['revenue', 'revenue']


def test_business_data_errors_are_not_retried(monkeypatch):
    pytest.importorskip('langgraph')
    from retailiq.domain.analytics import DomainDataError
    monkeypatch.setattr(graph, 'chat_model', lambda: _router_model())
    calls = []

    def corrupt_inventory(question):
        calls.append(question)
        raise DomainDataError('Inconsistent reserved quantity')

    monkeypatch.setattr(graph, 'inventory_analysis', corrupt_inventory)
    with pytest.raises(DomainDataError, match='reserved'):
        graph.build_graph().invoke({'question': 'What is the inventory stock of EL-001?'})
    assert len(calls) == 1


def test_independent_checkpointer_threads_do_not_share_answers(monkeypatch, tmp_path):
    pytest.importorskip('langgraph')
    from langgraph.checkpoint.sqlite import SqliteSaver
    monkeypatch.setattr(graph, 'chat_model', lambda: _router_model())
    monkeypatch.setattr(graph, 'sales_analysis', lambda q,c:
                        {'answer': 'A-sales', 'records': [], 'contexts': []})
    monkeypatch.setattr(graph, 'inventory_analysis', lambda q:
                        {'answer': 'B-stock', 'records': [], 'contexts': []})
    path = tmp_path / 'isolated.sqlite3'
    with SqliteSaver.from_conn_string(str(path)) as saver:
        compiled = graph.build_graph(checkpointer=saver)
        a = {'configurable': {'thread_id': 'A'}}
        b = {'configurable': {'thread_id': 'B'}}
        compiled.invoke({'question': 'What is revenue?'}, config=a)
        compiled.invoke({'question': 'How much stock for EL-001?'}, config=b)
        assert compiled.get_state(a).values['answer'] == 'A-sales'
        assert compiled.get_state(b).values['answer'] == 'B-stock'
        assert compiled.get_state(a).values['active_agent'] == 'sales_agent'
        assert compiled.get_state(b).values['active_agent'] == 'inventory_agent'


def test_failed_graph_turn_does_not_reuse_previously_successful_answer(monkeypatch, tmp_path):
    pytest.importorskip('langgraph')
    from langgraph.checkpoint.sqlite import SqliteSaver
    monkeypatch.setattr(graph, 'chat_model', lambda: _router_model())
    calls = []
    def tool(question, category):
        calls.append(1)
        if len(calls) == 2:
            raise ValueError('Forced failure')
        return {'answer': 'Verified first answer', 'records': [], 'contexts': []}
    monkeypatch.setattr(graph, 'sales_analysis', tool)
    with SqliteSaver.from_conn_string(str(tmp_path / 'failure.sqlite3')) as saver:
        compiled = graph.build_graph(checkpointer=saver)
        config = {'configurable': {'thread_id': 'same-thread'}}
        first = compiled.invoke({'question': 'What is revenue this month?',
                                 'answer': '', 'records': [], 'contexts': [],
                                 'handoff': None}, config=config)
        assert first['answer'] == 'Verified first answer'
        with pytest.raises(ValueError, match='Forced failure'):
            compiled.invoke({'question': 'What is revenue this month?',
                             'answer': '', 'records': [], 'contexts': [],
                             'handoff': None}, config=config)
        third = compiled.invoke({'question': 'Which products are top sellers?',
                                 'answer': '', 'records': [], 'contexts': [],
                                 'handoff': None}, config=config)
        assert third['answer'] == 'Verified first answer'
        assert len(calls) == 3


def test_checkpoint_graph_has_explicit_close_and_path_isolation(monkeypatch, tmp_path):
    pytest.importorskip('langgraph')
    graph.close_checkpoint_graph()
    first = tmp_path / 'one.sqlite3'
    second = tmp_path / 'two.sqlite3'
    monkeypatch.setenv('RETAILIQ_CHECKPOINT_DB', str(first))
    try:
        g1 = graph._session_graph()
        assert g1 is graph._session_graph()
        conn = graph._CHECKPOINT_CACHE['connection']
        assert graph._CHECKPOINT_CACHE['path'] == first
        monkeypatch.setenv('RETAILIQ_CHECKPOINT_DB', str(second))
        with pytest.raises(RuntimeError, match='Checkpoint database path changed'):
            graph._session_graph()
        graph.close_checkpoint_graph()
        with pytest.raises(sqlite3.ProgrammingError):
            conn.execute('SELECT 1')
        g2 = graph._session_graph()
        assert g2 is not g1
        assert graph._CHECKPOINT_CACHE['path'] == second
    finally:
        graph.close_checkpoint_graph()
