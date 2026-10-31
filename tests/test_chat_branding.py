"""RetailIQ Week 1 branding and chat-avatar contract.

Brand assets are static SVGs; no user authentication or profile photos are implied.
"""
from fastapi.testclient import TestClient
from retailiq.api import app

client = TestClient(app)


def test_brand_assets_served_as_local_svg():
    for name in ("logo-mark", "mascot-avatar", "mascot-guide"):
        response = client.get(f"/assets/brand/{name}.svg")
        assert response.status_code == 200
        assert "image/svg+xml" in response.headers["content-type"]
        assert "<svg" in response.text
        assert "http://" not in response.text.replace("http://www.w3.org/2000/svg", "")
        assert "<script" not in response.text.lower()


def test_logo_favicon_and_compact_chat_markup():
    html = client.get("/").text
    assert '<link rel="icon" type="image/svg+xml" href="/assets/brand/logo-mark.svg">' in html
    assert 'class="brand-wordmark"' in html
    assert 'id="chat-welcome"' in html
    assert 'id="active-response"' in html
    assert 'id="active-agent-avatar" class="agent-avatar agent-avatar-iq"' in html
    assert 'src="/assets/brand/mascot-guide.svg"' not in html
    assert '<strong>Ask RetailIQ</strong>' in html
    assert 'id="tab-workflows"' not in html
    assert 'id="graph-mode-request"' in html
    assert 'id="graph-mode-scenario"' in html
    assert '/assets/tool-workspace.css' in html
    assert "class=\"hero\"" not in html
    assert "Cost &amp; ROI" in html
    assert 'id="records-table"' in html


def test_avatar_added_to_history_and_new_turn():
    js = client.get("/assets/app.js").text
    assert "AgentID().avatar(agentType)" in js
    assert "setActiveAgent(result.active_agent, result.intent)" in js
    assert "avatar.className = 'chat-avatar chat-avatar-user'" in js
    assert "byId('chat-welcome').hidden = messages.length > 0" in js
    assert "byId('active-response').hidden = !last" in js
    assert "byId('active-response').hidden = false" in js
    css = client.get("/assets/data-workspace.css").text
    assert ".agent-avatar {" in css
    assert ".chat-welcome[hidden],.chat-active-answer[hidden]" in css
    assert ".chat-message-assistant .chat-bubble" in css
    assert '[data-agent=sales]' in css
    assert '[data-agent=inventory]' in css
    assert '[data-agent=product]' in css
    assert '[data-agent=supervisor]' in css
