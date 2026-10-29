"""Week 1 data-first UI contract; backend endpoints remain unchanged."""
from fastapi.testclient import TestClient
from retailiq.api import app

client = TestClient(app)


def test_no_landing_hero_and_data_grid_is_primary():
    html = client.get('/').text
    assert 'class="hero"' not in html
    assert 'Better retail answers.' not in html
    assert 'Ask RetailIQ anything.' not in html
    assert 'class="site-footer"' not in html
    assert html.index('id="chat-history"') < html.index('id="answer"') < html.index('id="ask-form"')
    assert html.index('id="ask-form"') < html.index('id="records-table"')
    assert 'role="log"' in html
    assert 'Run query' not in html
    assert 'Conversation history</summary>' not in html
    assert 'data-question="Which products are top sellers?"' in html
    assert 'id="tab-assistant"' in html
    assert 'id="tab-workflows"' not in html
    assert 'id="graph-mode-request"' in html
    assert 'id="graph-mode-scenario"' in html
    assert html.index('id="assistant-panel"') < html.index('id="workflows-panel"') < html.index('id="logs-panel"')
    for marker in ('id="records-table-wrap"', 'id="data-count"', 'id="source-list"',
                   'id="export-csv"', 'id="summary-agent"', 'id="summary-period"',
                   'id="summary-mode"', 'id="live-trace-list"', 'id="chat-history"'):
        assert marker in html


def test_compact_assets_and_safe_data_rendering():
    response = client.get('/assets/data-workspace.css')
    assert response.status_code == 200
    assert 'text/css' in response.headers['content-type']
    css = response.text
    assert '#records-table th' in css
    assert 'max-width:520px' in css
    assert 'linear-gradient' not in css
    js = client.get('/assets/app.js').text
    assert 'function renderRecords(' in js
    assert 'function exportRecordsCsv(' in js
    assert "td.textContent = formatCell(record[col])" in js
    assert 'li.textContent = source' in js
    assert "if (typeof value === 'string'" in js


def test_core_ui_and_tabs_remain_accessible():
    html = client.get('/').text
    for marker in ('id="ask-form"', 'id="chat-session-picker"',
                   'id="roi-panel"', 'id="roi-form"', 'id="roi-net"',
                   'id="logs-panel"', 'id="log-scope"', 'id="log-level"'):
        assert marker in html
    assert 'Cost &amp; ROI' in html
    assert 'illustrative' in html.lower()
    assert 'OPENAI_API_KEY' not in html
    assert 'LANGSMITH_API_KEY' not in html


def test_conversation_persists_messages_without_duplicate_latest_answer():
    html = client.get('/').text
    assert 'class="conversation-workspace"' in html
    assert 'id="chat-thread"' in html
    assert 'id="active-response"' in html
    js = client.get('/assets/app.js').text
    assert 'function appendChatMessage(' in js
    assert "if (i === final) continue;" in js
    assert 'currentAnswerIsPersisted' in js
    assert 'await selectSession(sessionId, true)' in js
    assert 'last && last.evidence ? last.evidence : {}' in js
    assert "Rich().renderEvidence(byId('response-visuals'), storedEvidence)" in js
    assert 'renderRecords(storedEvidence)' in js
    assert "appendChatMessage('user', question)" in js
    assert "scrollChatToBottom()" in js
