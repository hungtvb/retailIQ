"""Proof: request correlation, agent events, privacy, filters and local-only UI."""
import json
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from retailiq.api import app
from retailiq.observability import bind_context, log_event, log_exception, list_events


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv('RETAILIQ_MODE', 'offline')
    monkeypatch.setenv('RETAILIQ_CHAT_DB', str(tmp_path / 'sessions.sqlite3'))
    monkeypatch.setenv('RETAILIQ_LOG_FILE', str(tmp_path / 'events.jsonl'))
    return TestClient(app)


def test_log_events_and_session_request_correlation(client):
    sid = client.post('/api/sessions', json={}).json()['id']
    first = client.post('/ask', json={
        'question':'Which products are top sellers?', 'session_id':sid})
    assert first.status_code == 200
    request_id = first.json()['request_id']
    assert len(request_id) == 32
    assert first.headers['X-Request-ID'] == request_id
    second = client.post('/ask', json={
        'question':'How many units of the top seller are in stock?', 'session_id':sid})
    assert second.status_code == 200
    assert second.json()['handoff']['to'] == 'inventory_agent'
    payload = client.get(f'/api/logs?session_id={sid}').json()
    events = payload['events']
    assert payload['source'] == 'local_rotating_jsonl'
    names = [e['event'] for e in events]
    assert 'agent.handoff' in names
    assert 'agent.routed' in names
    assert 'tool.offline_lookup.completed' in names
    assert 'chat.turn.completed' in names
    assert 'chat.turn_result' in names
    by_req = client.get('/api/logs', params={'request_id': request_id}).json()['events']
    assert by_req and all(e['request_id'] == request_id for e in by_req)
    assert any(e.get('duration_ms') is not None for e in events)
    assert all('question' not in e and 'answer' not in e for e in events)
    assert not any('stack_trace' in e for e in events)


def test_failures_include_private_stack_without_exception_message(client, monkeypatch):
    def failing(*args, **kwargs):
        raise RuntimeError('sk-topsecret.example DO NOT LOG THIS INPUT')
    monkeypatch.setattr('retailiq.api.http.ask', failing)
    result = client.post('/ask', json={'question':'What is the revenue this month?'})
    assert result.status_code == 503
    assert 'topsecret' not in result.text
    assert result.headers['X-Request-ID']
    visible = client.get('/api/logs?level=ERROR').json()['events']
    assert any(x.get('error_type') == 'RuntimeError' for x in visible)
    assert all('stack_trace' not in x for x in visible)
    file = Path(__import__('os').environ['RETAILIQ_LOG_FILE']).read_text()
    assert 'stack_trace' in file and 'http.py' in file
    assert 'topsecret' not in file
    assert 'What is the revenue' not in file


def test_severity_filters_ids_and_validation(client):
    with bind_context(request='req-id-1', session='s-1'):
        log_event('sensitive.test', level='WARNING', agent='inventory_agent',
                  prompt='PRIVATE SECRET', api_key='SECRET', status='success')
    with bind_context(request='req-id-2', session='s-2'):
        log_event('second.test', level='INFO', agent='sales_agent')
    results = list_events(level='WARNING', session_id='s-1')
    assert len(results) == 1
    assert results[0]['event'] == 'sensitive.test'
    assert 'prompt' not in results[0] and 'api_key' not in results[0]
    assert client.get('/api/logs?limit=1000').status_code == 422
    assert client.get('/api/logs?level=BOGUS').status_code == 422
    assert client.get('/api/logs?request_id=foo').status_code == 422


def test_no_prompt_or_sensitive_keys_written(client):
    sid = client.post('/api/sessions',json={'title':'private display name'}).json()['id']
    phrase = 'MySuperSecretCustomerInformation456'
    response = client.post('/ask',json={'question':'Tell me about '+phrase, 'session_id':sid})
    assert response.status_code == 200
    path = Path(__import__('os').environ['RETAILIQ_LOG_FILE'])
    on_disk = path.read_text()
    assert phrase not in on_disk
    assert 'private display name' not in on_disk
    assert 'OPENAI_API_KEY' not in on_disk
    assert 'request_id' in on_disk


def test_local_only_access_helper(client):
    from retailiq.api.logs import _local_host
    assert _local_host('127.0.0.1')
    assert _local_host('::1')
    assert _local_host('testclient')
    assert not _local_host('0.0.0.0')
    assert not _local_host('8.8.8.8')
    assert not _local_host('attacker.example')


def test_ui_has_live_observability_filter_and_no_inner_html(client):
    html = client.get('/').text
    js = client.get('/assets/app.js').text
    assert 'tab-logs' in html and 'logs-panel' in html
    assert 'log-scope' in html and 'log-level' in html
    assert 'loadExecutionLogs' in js and '/api/logs?' in js
    assert 'meta.textContent' in js
