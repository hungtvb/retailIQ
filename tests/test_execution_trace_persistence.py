"""Execution trace evidence: durable, request-scoped, redacted and deleted with its session."""
import json
from fastapi.testclient import TestClient
from retailiq.api import app
from retailiq.infrastructure.sessions import save_execution_trace, get_execution_trace


def test_trace_persisted_and_request_scoped(tmp_path, monkeypatch):
    monkeypatch.setenv('RETAILIQ_MODE', 'offline')
    monkeypatch.setenv('RETAILIQ_CHAT_DB', str(tmp_path / 'sessions.sqlite3'))
    monkeypatch.setenv('RETAILIQ_LOG_FILE', str(tmp_path / 'events.jsonl'))
    client = TestClient(app)
    first = client.post('/api/sessions', json={}).json()['id']
    second = client.post('/api/sessions', json={}).json()['id']

    response = client.post('/ask/stream', json={
        'question':'Which products are top sellers?', 'session_id':first})
    frames = [chunk for chunk in response.text.split('\\n\\n') if 'event: result' in chunk]
    assert response.status_code == 200 and frames
    result = json.loads(frames[0].split('data: ', 1)[1])
    rid = result['request_id']
    messages = client.get(f'/api/sessions/{first}').json()['messages']
    assert messages[-1]['role'] == 'assistant' and messages[-1]['request_id'] == rid

    trace_response = client.get(f'/api/sessions/{first}/traces/{rid}')
    assert trace_response.status_code == 200
    trace = trace_response.json()
    assert trace['status'] == 'complete' and not trace['truncated']
    assert trace['request_id'] == rid
    assert any(e['event'] == 'agent.routed' for e in trace['events'])
    assert any(e['event'] == 'tool.offline_lookup.completed' for e in trace['events'])
    assert all(e['request_id'] == rid and e['session_id'] == first for e in trace['events'])
    assert all('answer' not in e and 'prompt' not in e and 'stack_trace' not in e
               for e in trace['events'])
    assert client.get(f'/api/sessions/{second}/traces/{rid}').status_code == 404
    assert client.get(f'/api/sessions/{first}/traces/no-such-trace').status_code == 404
    assert client.delete(f'/api/sessions/{first}').status_code == 204
    assert client.get(f'/api/sessions/{first}/traces/{rid}').status_code == 404


def test_trace_rejects_unsaved_turn_and_redacts_fields(tmp_path, monkeypatch):
    monkeypatch.setenv('RETAILIQ_CHAT_DB', str(tmp_path / 'sessions.sqlite3'))
    client = TestClient(app)
    first = client.post('/api/sessions', json={}).json()['id']
    assert not save_execution_trace(first, 'not-a-turn', [
        {'event':'agent.routed','request_id':'not-a-turn','session_id':first}])
    assert get_execution_trace(first, 'not-a-turn') is None

    result = client.post('/ask/stream', json={
        'question':'Which products are top sellers?', 'session_id':first})
    frames = [x for x in result.text.split('\\n\\n') if 'event: result' in x]
    rid = json.loads(frames[0].split('data: ', 1)[1])['request_id']
    good = {'event':'agent.routed','request_id':rid,'session_id':first,
            'agent':'sales_agent','prompt':'SECRET', 'answer':'PRIVATE',
            'stack_trace':[{'file':'secret.py'}]}
    bad = {'event':'agent.routed','request_id':'another-request',
           'session_id':first, 'agent':'inventory_agent'}
    assert save_execution_trace(first, rid, [good, bad])
    events = client.get(f'/api/sessions/{first}/traces/{rid}').json()['events']
    assert len(events) == 1 and events[0]['agent'] == 'sales_agent'
    assert 'prompt' not in events[0] and 'answer' not in events[0]
    assert 'stack_trace' not in events[0]


def test_repeated_questions_have_separate_trace_ids(tmp_path, monkeypatch):
    monkeypatch.setenv('RETAILIQ_MODE', 'offline')
    monkeypatch.setenv('RETAILIQ_CHAT_DB', str(tmp_path / 'sessions.sqlite3'))
    monkeypatch.setenv('RETAILIQ_LOG_FILE', str(tmp_path / 'events.jsonl'))
    client=TestClient(app)
    sid=client.post('/api/sessions',json={}).json()['id']
    for question in ('Which products are top sellers?', 'What is the revenue this month?'):
        response=client.post('/ask/stream',json={'question':question,'session_id':sid})
        assert response.status_code == 200
    turns=[m for m in client.get(f'/api/sessions/{sid}').json()['messages'] if m['role']=='assistant']
    assert len(turns)==2 and turns[0]['request_id']!=turns[1]['request_id']
    for turn in turns:
        trace=client.get(f"/api/sessions/{sid}/traces/{turn['request_id']}")
        assert trace.status_code == 200
        assert trace.json()['events']
