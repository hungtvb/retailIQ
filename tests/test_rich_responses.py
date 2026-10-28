"""Pure frontend response-format contract: safe Markdown + SQL-backed analytics.

This is structural integration coverage; real provider/visual E2E is separate.
"""
from fastapi.testclient import TestClient
from retailiq.api import app

client = TestClient(app)


def test_scripts_load_in_order_and_chat_mounts_rich_outputs():
    html = client.get("/").text
    assert html.index('/assets/agent-identity.js') < html.index('/assets/response-format.js') < html.index('/assets/app.js')
    assert 'id="response-visuals"' in html
    assert 'class="answer rich-markdown"' in html
    assert 'id="evidence-agent"' in html
    assert 'id="active-agent-avatar"' in html


def test_markup_is_constructed_as_dom_not_raw_llm_html():
    js = client.get("/assets/response-format.js").text
    assert 'function renderMarkdown(target, source)' in js
    assert 'function renderEvidence(target, result)' in js
    assert "target.replaceChildren()" in js
    assert "document.createTextNode" in js
    assert "el.textContent" in js
    assert "target.innerHTML" not in js
    assert "safeLink" in js
    assert "noopener noreferrer nofollow" in js
    assert "function delimiter(" in js
    assert "rich-code-block" in js
    assert "rich-md-table" in js
    assert "rich-citations" in js


def test_sql_driven_kpis_without_llm_fabricated_numbers():
    js = client.get("/assets/response-format.js").text
    assert "intent === 'stock'" in js
    assert "intent === 'revenue'" in js
    assert "intent === 'top'" in js
    for source_col in ("available", "net_revenue_vnd", "units_sold"):
        assert source_col in js
    assert "records.reduce" in js
    assert "result?.records" in js
    assert "Calculated from returned SQL records" in js


def test_agent_identity_is_allowlisted_and_covers_all_week1_specialists():
    identity = client.get("/assets/agent-identity.js").text
    for name in ("supervisor", "sales", "inventory", "product", "iq", "user"):
        assert name + ":" in identity
    assert "TYPES[id] ? id : 'iq'" in identity
    assert "node.dataset.agent = safe" in identity
    js = client.get("/assets/app.js").text
    assert "Rich().renderMarkdown" in js
    assert "Rich().renderEvidence" in js
    assert "AgentID().type" in js
    assert "AgentID().apply" in js


def test_rich_response_ui_remains_compact_and_responsive():
    css = client.get("/assets/data-workspace.css").text
    for required in (".rich-markdown", ".rich-code-block", ".rich-metrics",
                     ".rich-bars", ".rich-citations", ".agent-avatar",
                     ".agent-badge", ".rich-table-scroll"):
        assert required in css
    assert "@media(max-width:520px)" in css
    assert "linear-gradient" not in css
