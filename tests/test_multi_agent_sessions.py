"""Acceptance scenarios for Week 1 FDE: session history + 4 patterns."""
import pytest
from fastapi.testclient import TestClient
from retailiq.api import app
from retailiq.infrastructure import sessions
from retailiq.orchestration.week1_graph import classify, resolve_followup
from retailiq.skills import load_skill


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv('RETAILIQ_CHAT_DB', str(tmp_path / 'conversations.sqlite3'))
    monkeypatch.setenv('RETAILIQ_MODE', 'offline')
    return TestClient(app)


def test_create_list_get_delete_session(client):
    session = client.post('/api/sessions', json={}).json()
    sid = session['id']
    assert session['title'] == 'New conversation'
    assert any(s['id'] == sid for s in client.get('/api/sessions').json()['sessions'])
    assert client.get(f'/api/sessions/{sid}').json()['messages'] == []
    assert client.delete(f'/api/sessions/{sid}').status_code == 204
    assert client.get(f'/api/sessions/{sid}').status_code == 404


def test_history_survives_reopen_and_isolates_sessions(client):
    a = client.post('/api/sessions', json={}).json()['id']
    b = client.post('/api/sessions', json={}).json()['id']
    q = 'Tell me about USB-C GaN Charger 65W'
    assert client.post('/ask', json={'question': q, 'session_id': a}).status_code == 200
    assert len(client.get(f'/api/sessions/{a}').json()['messages']) == 2
    assert client.get(f'/api/sessions/{b}').json()['messages'] == []
    assert client.get(f'/api/sessions/{a}').json()['title'] == q
    assert client.post('/ask',json={'question':'What about its stock?', 'session_id': a}).json()['intent'] == 'stock'
    assert len(client.get(f'/api/sessions/{a}').json()['messages']) == 4


def test_sales_to_inventory_real_handoff_metadata(client):
    sid=client.post('/api/sessions', json={}).json()['id']
    first=client.post('/ask',json={'question':'Which products are top sellers?', 'session_id':sid}).json()
    assert first['active_agent']=='sales_agent'
    second=client.post('/ask',json={'question':'How many units of the top seller are in stock?', 'session_id':sid}).json()
    assert second['active_agent']=='inventory_agent'
    assert second['handoff']=={'from':'sales_agent','to':'inventory_agent',
                               'reason':'Follow-up inventory question'}
    assert 'available units' in second['answer']
    assert client.get(f'/api/sessions/{sid}').json()['active_agent']=='inventory_agent'


def test_supervisor_subagents_skill_decision(client):
    sid=client.post('/api/sessions',json={}).json()['id']
    response=client.post('/ask',json={
        'question':'Which top seller needs a replenishment review based on stock?', 'session_id':sid
    })
    assert response.status_code == 200
    payload=response.json()
    assert payload['intent']=='decision'
    assert payload['active_agent']=='retail_supervisor'
    assert payload['subagents']==['sales_agent','inventory_agent']
    assert payload['skill']=='replenishment_review'
    assert 'Not a forecast' in payload['answer']


def test_skills_are_allowlisted_and_not_generic_docs():
    assert 'Revenue' in load_skill('sales_kpi')
    assert 'Available units' in load_skill('inventory_availability')
    with pytest.raises(ValueError):load_skill('../.env')


def test_bad_session_no_chat_side_effect(client):
    response=client.post('/ask',json={'question':'What is the revenue this month?',
                                      'session_id':'00000000-0000-0000-0000-000000000000'})
    assert response.status_code==404


def test_router_cross_domain_and_followup_resolution():
    assert classify('Which top seller needs replenishment based on stock?')=='decision'
    assert classify('What is the revenue this month?')=='revenue'
    effective=resolve_followup('What about its stock?',
        [{'role':'user','content':'Tell me about USB-C GaN Charger 65W'}])
    assert 'EL-' in effective


def test_ui_has_session_and_agent_evidence(client):
    html=client.get('/').text
    assert 'chat-session-picker' in html
    assert 'agent-trace' in html
    js=client.get('/assets/app.js').text
    assert 'refreshSessions' in js
    assert 'showAgentEvidence' in js
