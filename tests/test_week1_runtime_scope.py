"""Week 1-only runtime checks: sessions, bounded provider calls, read-only retries.

Approval workflows and advanced fault tolerance belong to later weeks.
"""
import sqlite3
import sys
import types
from fastapi.testclient import TestClient
import pytest
from retailiq.api import app
from retailiq.infrastructure.sessions import session_mutation
from retailiq.orchestration import week1_graph as graph


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv('RETAILIQ_CHAT_DB', str(tmp_path / 'chat.sqlite3'))
    monkeypatch.setenv('RETAILIQ_CHECKPOINT_DB', str(tmp_path / 'checkpoints.sqlite3'))
    monkeypatch.setenv('RETAILIQ_MODE', 'offline')
    return TestClient(app)


def test_same_session_busy_rejected_without_new_turn(client):
    sid = client.post('/api/sessions', json={}).json()['id']
    with session_mutation(sid):
        res = client.post('/ask', json={'question': 'What is the revenue this month?', 'session_id': sid})
        assert res.status_code == 409
        assert client.delete(f'/api/sessions/{sid}').status_code == 409
        event_response = client.post('/ask/stream', json={
            'question': 'Which products are top sellers?', 'session_id': sid})
        assert '"code":"session_busy"' in event_response.text
    assert client.get(f'/api/sessions/{sid}').json()['messages'] == []
    assert client.delete(f'/api/sessions/{sid}').status_code == 204


def test_deleting_session_cleans_checkpoint_before_chat_row(client, tmp_path, monkeypatch):
    sid = client.post('/api/sessions', json={}).json()['id']
    db = tmp_path / 'checkpoints.sqlite3'
    db.write_text('mock checkpoint exists')
    cleaned = []
    fake = types.SimpleNamespace(checkpointer=types.SimpleNamespace(
        delete_thread=lambda thread_id: cleaned.append(thread_id)))
    monkeypatch.setattr(graph, '_session_graph', lambda: fake)
    assert client.delete(f'/api/sessions/{sid}').status_code == 204
    assert cleaned == [sid]
    assert client.get(f'/api/sessions/{sid}').status_code == 404


def test_failed_checkpoint_cleanup_preserves_session(client, tmp_path, monkeypatch):
    sid = client.post('/api/sessions', json={}).json()['id']
    (tmp_path / 'checkpoints.sqlite3').write_text('mock')
    def fail(sid):
        raise sqlite3.OperationalError('unavailable')
    monkeypatch.setattr(graph, '_session_graph', lambda: types.SimpleNamespace(
        checkpointer=types.SimpleNamespace(delete_thread=fail)))
    assert client.delete(f'/api/sessions/{sid}').status_code == 503
    assert client.get(f'/api/sessions/{sid}').status_code == 200


def test_read_only_retry_policy_rejects_semantic_and_permission_errors():
    assert graph.retryable_read_failure(TimeoutError())
    assert graph.retryable_read_failure(ConnectionError())
    assert graph.retryable_read_failure(sqlite3.OperationalError('database is locked'))
    assert graph.retryable_read_failure(sqlite3.OperationalError('database is busy'))
    assert not graph.retryable_read_failure(sqlite3.OperationalError('no such table'))
    assert not graph.retryable_read_failure(ValueError('invalid SKU'))
    assert not graph.retryable_read_failure(PermissionError('not allowed'))


def test_provider_timeout_and_max_one_retry(monkeypatch):
    from retailiq.core import config
    fake = types.ModuleType('langchain_openai')
    class Factory:
        def __init__(self, **kw): self.kw = kw
    fake.ChatOpenAI = Factory
    fake.OpenAIEmbeddings = Factory
    monkeypatch.setitem(sys.modules, 'langchain_openai', fake)
    monkeypatch.setenv('OPENAI_BASE_URL', 'https://gateway.example.com/v1/')
    monkeypatch.setenv('OPENAI_API_KEY', 'fake-key')
    monkeypatch.setenv('RETAILIQ_PROVIDER_TIMEOUT_SECONDS', '7')
    model, embed = config.chat_model(), config.embeddings_model()
    assert model.kw['timeout'] == 7.0
    assert embed.kw['request_timeout'] == 7.0
    assert model.kw['max_retries'] == embed.kw['max_retries'] == 1
    monkeypatch.setenv('RETAILIQ_PROVIDER_TIMEOUT_SECONDS', '0')
    with pytest.raises(ValueError): config.chat_model()
    monkeypatch.setenv('RETAILIQ_PROVIDER_TIMEOUT_SECONDS', 'abc')
    with pytest.raises(ValueError): config.embeddings_model()


def test_missing_full_mode_module_reports_actionable_error_in_chat_and_stream(client, monkeypatch):
    from retailiq.api import http

    def missing(*_args, **_kwargs):
        raise ModuleNotFoundError("No module named 'langgraph.checkpoint.sqlite'",
                                  name='langgraph.checkpoint.sqlite')

    monkeypatch.setattr(http, 'ask', missing)
    response = client.post('/ask', json={'question': 'What is the revenue this month?'})
    assert response.status_code == 503
    detail = response.json()['detail']
    assert 'langgraph.checkpoint.sqlite' in detail
    assert 'requirements-full.txt' in detail

    stream = client.post('/ask/stream', json={'question': 'What is the revenue this month?'})
    assert stream.status_code == 200
    assert '"code":"dependency_missing"' in stream.text
    assert 'langgraph.checkpoint.sqlite' in stream.text
    assert 'requirements-full.txt' in stream.text


def test_missing_private_module_never_reflects_untrusted_import_name():
    from retailiq.api.http import _missing_module_message

    error = ModuleNotFoundError('No module named sensitive_secret_project',
                                name='sensitive_secret_project')
    message = _missing_module_message(error)
    assert 'sensitive_secret_project' not in message
    assert 'requirements-full.txt' in message
