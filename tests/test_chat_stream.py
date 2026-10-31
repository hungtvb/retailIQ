"""SSE acceptance: real backend events, completion, isolation, failures, privacy."""
import json
import os
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from retailiq.api import app
from retailiq.observability import bind_context, bind_event_sink, log_event


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv('RETAILIQ_MODE', 'offline')
    monkeypatch.setenv('RETAILIQ_CHAT_DB', str(tmp_path / 'sessions.sqlite3'))
    monkeypatch.setenv('RETAILIQ_LOG_FILE', str(tmp_path / 'events.jsonl'))
    return TestClient(app)


def parse_sse(text):
    messages = []
    for frame in text.split('\n\n'):
        if not frame.strip() or frame.startswith(':'):
            continue
        pairs = [line.split(':', 1) for line in frame.strip().split('\n') if ':' in line]
        fields = {k: v.lstrip() for k, v in pairs}
        messages.append((fields.get('event'), json.loads(fields.get('data', '{}'))))
    return messages


def test_stream_contains_live_backend_events_and_matching_request_id(client):
    sid = client.post('/api/sessions', json={}).json()['id']
    with client.stream('POST', '/ask/stream', json={'question': 'Which products are top sellers?', 'session_id': sid}) as resp:
        assert resp.status_code == 200
        assert resp.headers['content-type'].startswith('text/event-stream')
        assert 'no-store' in resp.headers['cache-control']
        rid = resp.headers['X-Request-ID']
        events = parse_sse(''.join(resp.iter_text()))
    names = [kind for kind, _ in events]
    assert names[0] == 'started'
    assert names[-1] == 'done'
    assert 'result' in names and 'log' in names
    assert names.index('log') < names.index('result')
    assert events[0][1]['request_id'] == rid
    logs = [payload for kind, payload in events if kind == 'log']
    assert any(x['event'] == 'agent.routed' and x['agent'] == 'sales_agent' for x in logs)
    assert any(x['event'] == 'tool.offline_lookup.completed' and 'duration_ms' in x for x in logs)
    assert all(x['request_id'] == rid and x['session_id'] == sid for x in logs)
    result = next(data for kind, data in events if kind == 'result')
    assert result['active_agent'] == 'sales_agent'
    assert result['request_id'] == rid
    assert len(client.get(f'/api/sessions/{sid}').json()['messages']) == 2
    disk = Path(os.environ['RETAILIQ_LOG_FILE']).read_text()
    assert 'agent.routed' in disk


def test_followup_handoff_stream_and_second_session_isolation(client):
    first = client.post('/api/sessions', json={}).json()['id']
    second = client.post('/api/sessions', json={}).json()['id']
    client.post('/ask/stream', json={'question':'Which products are top sellers?', 'session_id': first})
    r1 = client.post('/ask/stream', json={
        'question': 'How many units of the top seller are in stock?', 'session_id':first})
    r2 = client.post('/ask/stream', json={
        'question': 'What is the revenue this month?', 'session_id':second})
    e1, e2 = parse_sse(r1.text), parse_sse(r2.text)
    logs1 = [x for k, x in e1 if k == 'log']
    logs2 = [x for k, x in e2 if k == 'log']
    assert any(x['event'] == 'agent.handoff' for x in logs1)
    assert not any(x['event'] == 'agent.handoff' for x in logs2)
    assert all(x['session_id'] == first for x in logs1)
    assert all(x['session_id'] == second for x in logs2)
    assert next(x for k, x in e1 if k == 'result')['handoff']['to'] == 'inventory_agent'


def test_stream_failure_has_redacted_error_and_no_persisted_user_turn(client, monkeypatch):
    def fail(*args, **kwargs):
        log_event('agent.custom_step', agent='sales_agent', prompt='API_KEY=abc123')
        raise RuntimeError('API_KEY=abc123, private prompt')
    monkeypatch.setattr('retailiq.api.http.ask', fail)
    sid = client.post('/api/sessions', json={}).json()['id']
    response = client.post('/ask/stream', json={'question':'Tell me something secret', 'session_id':sid})
    messages = parse_sse(response.text)
    assert [k for k, _ in messages][-2:] == ['error','done']
    assert 'result' not in [k for k, _ in messages]
    assert 'abc123' not in response.text
    assert 'Tell me something secret' not in response.text
    assert all('stack_trace' not in event for kind, event in messages if kind == 'log')
    assert client.get(f'/api/sessions/{sid}').json()['messages'] == []
    assert 'abc123' not in Path(os.environ['RETAILIQ_LOG_FILE']).read_text()


def test_stream_invalid_session_and_invalid_input(client):
    response = client.post('/ask/stream', json={
        'question': 'Which products are top sellers?',
        'session_id': '00000000-0000-0000-0000-000000000000'})
    assert response.status_code == 404
    assert client.post('/ask/stream', json={'question':'no'}).status_code == 422


def test_sinks_are_scoped_and_strip_non_allowlisted_fields():
    events_a, events_b = [], []
    with bind_context(request='request-a', session='session-a'), bind_event_sink(events_a.append):
        log_event('agent.routed', agent='sales_agent', answer='HIDDEN', api_key='SECRET')
        with bind_event_sink(events_b.append):
            log_event('agent.handoff', target_agent='inventory_agent')
        log_event('tool.sql.completed', tool='inventory_analytics')
    assert len(events_a) == 2 and len(events_b) == 1
    assert all(e['session_id'] == 'session-a' for e in events_a)
    assert all('api_key' not in e and 'answer' not in e and 'stack_trace' not in e for e in events_a + events_b)


def test_chat_ui_uses_sse_with_in_place_live_trace(client):
    html = client.get('/').text
    js = client.get('/assets/app.js').text
    assert 'live-trace-list' in html
    assert 'class="live-trace-title"' in html
    assert 'id="live-trace-count"' in html
    assert "fetch('/ask/stream'" in js
    assert "type === 'log'" in js
    assert 'ReadableStream' not in js
    assert 'response.body.getReader()' in js
    assert 'textContent' in js


def test_first_sse_frame_arrives_before_slow_agent_completes(monkeypatch):
    """Prove the backend does not generate all events after finishing the job."""
    from types import SimpleNamespace
    from threading import Event
    import asyncio
    from retailiq.api import http
    original = http.ask
    entered = Event()
    allow_finish = Event()

    def slow_ask(*args, **kwargs):
        entered.set()
        assert allow_finish.wait(timeout=3)
        return original(*args, **kwargs)

    monkeypatch.setenv('RETAILIQ_MODE', 'offline')
    monkeypatch.setattr(http, 'ask', slow_ask)
    req = SimpleNamespace(state=SimpleNamespace(request_id='streaming-test-req'))
    response = http.stream_answer(http.AskBody(question='Which products are top sellers?'), req)

    async def inspect():
        stream = response.body_iterator
        first_frame = await stream.__anext__()
        assert b'event: started' in first_frame.encode() if isinstance(first_frame,str) else b'event: started' in first_frame
        assert entered.wait(timeout=2)
        assert not allow_finish.is_set()
        allow_finish.set()
        frames = [first_frame]
        async for frame in stream:
            frames.append(frame)
        complete = ''.join(x.decode() if isinstance(x, bytes) else x for x in frames)
        assert 'event: log' in complete and 'event: result' in complete
        assert complete.index('event: log') < complete.index('event: result')
    try:
        asyncio.run(inspect())
    finally:
        allow_finish.set()
