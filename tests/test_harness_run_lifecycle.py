"""H1-A1: observable run lifecycle never outruns business/session commit.

Mocked assistant only: these tests protect truthful events, not LLM/business
correctness. Real agent and MCP provider gates remain separate.
"""
from contextlib import contextmanager, nullcontext

import pytest

from retailiq.api import http
from retailiq.observability import bind_context, bind_event_sink

SESSION = '00000000-0000-0000-0000-000000000001'


def _answer():
    return {'answer': 'Verified fixture answer', 'intent': 'stock',
            'active_agent': 'inventory_agent', 'records': [], 'contexts': []}


def _session_fixture(monkeypatch):
    monkeypatch.setattr(http, 'session_mutation', lambda sid: nullcontext())
    monkeypatch.setattr(http, 'get_session', lambda sid, include_messages=False:
                        {'active_agent': 'sales_agent'})
    monkeypatch.setattr(http, 'history', lambda sid, limit: [])
    monkeypatch.setattr(http, 'get_customer_memory', lambda sid: {'consent': False})
    monkeypatch.setattr(http, 'last_committed_case_binding', lambda sid: None)


def _names(events):
    return [event['event'] for event in events]


def test_stateless_success_never_claims_session_commit(monkeypatch, tmp_path):
    monkeypatch.setenv('RETAILIQ_MODE', 'full')
    monkeypatch.setenv('RETAILIQ_LOG_FILE', str(tmp_path / 'events.jsonl'))
    monkeypatch.setattr(http, 'ask', lambda question: _answer())
    monkeypatch.setattr(http, 'add_turn', lambda *a, **kw:
                        pytest.fail('Stateless request must not commit'))
    events = []
    with bind_context(request='stateless-run'), bind_event_sink(events.append):
        result = http._perform_turn(http.AskBody(question='Sensitive inventory question'))
    assert result['answer'] == 'Verified fixture answer'
    assert result['session_id'] is None and result['request_id'] == 'stateless-run'
    assert _names(events).count('harness.run_started') == 1
    assert _names(events).count('harness.run_completed') == 1
    assert 'harness.turn_committed' not in _names(events)
    assert 'harness.run_verified' not in _names(events)  # graph must own verification
    assert 'Sensitive inventory question' not in str(events)
    assert 'Verified fixture answer' not in str(events)


def test_session_completion_follows_successful_persistence(monkeypatch, tmp_path):
    monkeypatch.setenv('RETAILIQ_MODE', 'full')
    monkeypatch.setenv('RETAILIQ_LOG_FILE', str(tmp_path / 'events.jsonl'))
    _session_fixture(monkeypatch)
    committed = []
    calls = []
    monkeypatch.setattr(http, 'ask',
                        lambda question, **kwargs: (calls.append(kwargs), _answer())[1])
    monkeypatch.setattr(http, 'add_turn', lambda sid, question, result:
                        committed.append((sid, question, result)))
    events = []
    with bind_context(request='session-run', session=SESSION), bind_event_sink(events.append):
        result = http._perform_turn(http.AskBody(question='Find SKU stock', session_id=SESSION))
    assert result['request_id'] == 'session-run'
    assert len(committed) == 1 and committed[0][0] == SESSION
    assert committed[0][2]['request_id'] == 'session-run'
    assert calls[0]['active_agent'] == 'sales_agent'
    names = _names(events)
    assert names.index('harness.run_started') < names.index('harness.turn_committed')
    assert names.index('harness.turn_committed') < names.index('harness.run_completed')
    assert names.count('harness.turn_committed') == 1
    assert all(event.get('session_id') == SESSION and
               event.get('request_id') == 'session-run'
               for event in events if event['event'].startswith('harness.'))
    assert 'Find SKU stock' not in str(events)
    assert 'Verified fixture answer' not in str(events)


def test_failed_session_commit_cannot_emit_successful_final(monkeypatch, tmp_path):
    monkeypatch.setenv('RETAILIQ_MODE', 'full')
    monkeypatch.setenv('RETAILIQ_LOG_FILE', str(tmp_path / 'events.jsonl'))
    _session_fixture(monkeypatch)
    monkeypatch.setattr(http, 'ask', lambda question, **kwargs: _answer())

    def broken_commit(*args):
        raise OSError('secret customer data must not leak')

    monkeypatch.setattr(http, 'add_turn', broken_commit)
    events = []
    with bind_context(request='failed-commit', session=SESSION), bind_event_sink(events.append):
        with pytest.raises(OSError, match='secret customer'):
            http._perform_turn(http.AskBody(question='Sensitive purchase', session_id=SESSION))
    names = _names(events)
    assert 'harness.run_started' in names
    assert 'harness.turn_committed' not in names
    assert 'harness.run_completed' not in names
    stopped = [e for e in events if e['event'] == 'harness.run_stopped']
    assert len(stopped) == 1
    assert stopped[0]['status'] == 'failed'
    assert stopped[0]['stop_reason'] == 'SESSION_COMMIT_FAILED'
    assert stopped[0]['error_type'] == 'OSError'
    assert 'secret customer' not in str(events)
    assert 'Sensitive purchase' not in str(events)


def test_agent_exception_propagates_without_unverified_completion(monkeypatch, tmp_path):
    monkeypatch.setenv('RETAILIQ_MODE', 'full')
    monkeypatch.setenv('RETAILIQ_LOG_FILE', str(tmp_path / 'events.jsonl'))

    def broken_agent(question):
        raise ValueError('model output is not grounded')

    monkeypatch.setattr(http, 'ask', broken_agent)
    events = []
    with bind_context(request='failed-model'), bind_event_sink(events.append):
        with pytest.raises(ValueError, match='not grounded'):
            http._perform_turn(http.AskBody(question='Question before failed model'))
    names = _names(events)
    assert 'harness.run_completed' not in names
    assert 'harness.turn_committed' not in names
    assert next(e for e in events if e['event'] == 'harness.run_stopped')['stop_reason'] == 'EXECUTION_FAILED'
    assert 'model output is not grounded' not in str(events)


def test_missing_session_fails_before_business_execution(monkeypatch, tmp_path):
    monkeypatch.setenv('RETAILIQ_LOG_FILE', str(tmp_path / 'events.jsonl'))
    monkeypatch.setattr(http, 'session_mutation', lambda sid: nullcontext())
    monkeypatch.setattr(http, 'get_session', lambda sid, include_messages=False: None)
    monkeypatch.setattr(http, 'ask', lambda *args, **kw:
                        pytest.fail('Missing session cannot call model'))
    events = []
    with bind_context(request='missing-session', session=SESSION), bind_event_sink(events.append):
        with pytest.raises(http._SessionNotFound):
            http._perform_turn(http.AskBody(question='Check stock', session_id=SESSION))
    assert next(e for e in events if e['event'] == 'harness.run_stopped')['stop_reason'] == 'SESSION_NOT_FOUND'
    assert 'harness.run_completed' not in _names(events)


def test_busy_session_has_fixed_reason_without_execution(monkeypatch, tmp_path):
    monkeypatch.setenv('RETAILIQ_LOG_FILE', str(tmp_path / 'events.jsonl'))

    @contextmanager
    def busy_guard():
        raise http.SessionBusyError('Another request is active')
        yield

    monkeypatch.setattr(http, 'session_mutation', lambda sid: busy_guard())
    monkeypatch.setattr(http, 'ask', lambda *args, **kw:
                        pytest.fail('Busy session must not call model'))
    events = []
    with bind_context(request='busy-session', session=SESSION), bind_event_sink(events.append):
        with pytest.raises(http.SessionBusyError):
            http._perform_turn(http.AskBody(question='Check stock', session_id=SESSION))
    stopped = [e for e in events if e['event'] == 'harness.run_stopped']
    assert len(stopped) == 1 and stopped[0]['stop_reason'] == 'SESSION_BUSY'
    assert 'Another request is active' not in str(events)
    assert 'harness.run_completed' not in _names(events)
