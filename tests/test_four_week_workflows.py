"""Offline acceptance for the four-week synthetic workflows and manager gate."""
from datetime import date
import sqlite3

import pytest
from fastapi.testclient import TestClient

from retailiq.api import app
from scripts.seed import seed


@pytest.fixture
def client(tmp_path, monkeypatch):
    data = tmp_path / "retail.sqlite3"
    seed(data, write_support_files=False, reference_date=date(2026, 10, 28))
    monkeypatch.setenv("RETAILIQ_DATA_DB", str(data))
    monkeypatch.setenv("RETAILIQ_WORKFLOW_DB", str(tmp_path / "workflow.sqlite3"))
    monkeypatch.setenv("RETAILIQ_MODE", "offline")
    return TestClient(app), data


def submit(client, scenario, **kwargs):
    return client.post("/api/workflows/run", json={
        "scenario": scenario, "sku": "EL-003", "quantity": 2,
        "role": "analyst", **kwargs,
    })


def test_definitions_accurate_and_graph_connected(client):
    api, _ = client
    response = api.get("/api/workflows/definitions")
    assert response.status_code == 200
    scenarios = {item["id"]: item for item in response.json()["scenarios"]}
    assert set(scenarios) == {"week1", "week2", "week3", "alerts", "week4"}
    for scenario in scenarios.values():
        ids = {node["id"] for node in scenario["nodes"]}
        assert scenario["edges"]
        assert all(e["from"] in ids and e["to"] in ids for e in scenario["edges"])
        assert len(scenario["edges"]) >= len(ids) - 1
        assert scenario["execution"] == "deterministic_local_simulation"
    assert len([node for node in scenarios["week4"]["nodes"] if node["kind"] == "agent"]) == 5
    assert "not authentication" in response.json()["role_notice"]


def test_week2_semantics_and_stale_data_is_not_misrepresented(client):
    api, _ = client
    payload = submit(api, "week2").json()
    assert payload["status"] == "completed"
    assert [e["node"] for e in payload["events"]] == [
        "request", "inventory_mcp", "semantic_layer", "freshness_guard", "evidence"]
    assert "STALE" in payload["report"]
    assert "revenue" in payload["report"]
    assert "MCP network transport not exercised" in payload["events"][1]["detail"]


def test_week3_manager_gate_and_no_price_mutation(client):
    api, data = client
    before = sqlite3.connect(data).execute(
        "SELECT price_vnd FROM products WHERE sku='EL-003'").fetchone()[0]
    run = submit(api, "week3").json()
    assert run["status"] == "pending_manager"
    assert run["events"][-1]["status"] == "awaiting"
    url = "/api/workflows/runs/" + run["id"] + "/review"
    assert api.post(url, json={"role": "analyst", "decision": "approve"}).status_code == 403
    reviewed = api.post(url, json={"role": "manager", "decision": "approve"})
    assert reviewed.status_code == 200
    assert reviewed.json()["status"] == "approved_simulated"
    assert reviewed.json()["events"][-1]["node"] == "finalize"
    assert api.post(url, json={"role": "manager", "decision": "approve"}).status_code == 409
    after = sqlite3.connect(data).execute(
        "SELECT price_vnd FROM products WHERE sku='EL-003'").fetchone()[0]
    assert before == after


def test_week4_five_agents_handoffs_and_no_order_insert(client):
    api, data = client
    before = sqlite3.connect(data).execute("SELECT COUNT(*) FROM orders").fetchone()[0]
    run = submit(api, "week4").json()
    assert run["status"] == "pending_manager"
    ids = [event["node"] for event in run["events"]]
    for node in ("inventory_search_agent", "fulfilment_optimisation_agent",
                 "customer_context_agent", "dynamic_pricing_agent",
                 "order_management_agent", "verification", "manager_approval"):
        assert node in ids
    assert all(event["from"] == ids[i - 1] for i, event in enumerate(run["events"]) if i > 0)
    reviewed = api.post("/api/workflows/runs/" + run["id"] + "/review",
                        json={"role": "manager", "decision": "reject"})
    assert reviewed.status_code == 200
    assert reviewed.json()["status"] == "rejected"
    after = sqlite3.connect(data).execute("SELECT COUNT(*) FROM orders").fetchone()[0]
    assert before == after


def test_insufficient_stock_blocks_order_before_approval(client):
    api, data = client
    with sqlite3.connect(data) as db:
        db.execute("UPDATE inventory SET on_hand = reserved + 1 WHERE sku='EL-003'")
    result = submit(api, "week4", quantity=20).json()
    assert result["status"] == "blocked"
    assert result["events"][-1]["node"] == "verification"
    assert not any(x["node"] == "manager_approval" for x in result["events"])
    assert "BLOCKED" in result["report"]


def test_validation_and_missing_runs(client):
    api, _ = client
    assert submit(api, "week4", sku="UNKNOWN").status_code == 422
    assert submit(api, "week4", quantity=21).status_code == 422
    assert submit(api, "mystery").status_code == 422
    assert api.get("/api/workflows/runs/does-not-exist").status_code == 404
    assert api.post("/api/workflows/runs/does-not-exist/review",
                    json={"role":"manager","decision":"approve"}).status_code == 404


def test_kpi_alert_screening(client):
    api, data = client
    normal = submit(api, "alerts").json()
    assert "NORMAL" in normal["report"]
    with sqlite3.connect(data) as db:
        db.execute("UPDATE inventory SET on_hand=reserved+1 WHERE sku='EL-003'")
    alert = submit(api, "alerts").json()
    assert "ALERT" in alert["report"]
    assert "No notifications" in alert["events"][-1]["detail"]


def test_graph_ui_assets_and_sse_link(client):
    api, _ = client
    html = api.get("/").text
    graph = api.get("/assets/workflow-graph.js").text
    ui = api.get("/assets/workflow-ui.js").text
    appjs = api.get("/assets/app.js").text
    assert 'id="execution-graph"' in html
    assert 'id="workflow-graph"' in html
    assert 'id="workflow-review-controls"' in html
    assert "/assets/workflow-graph.js" in html
    assert "document.createElementNS" in graph
    assert "textContent" in graph
    assert "chatEvent(event)" in appjs
    assert "graph?.replay(result.events)" in ui


def test_mcp_adapter_is_only_claimed_when_actually_invoked(client, monkeypatch):
    api, _ = client
    import retailiq.mcp_adapter as adapter
    from retailiq.domain.analytics import inventory
    calls = []
    def fake_mcp(sku):
        calls.append(sku)
        return inventory(sku)
    monkeypatch.setattr(adapter, "read_inventory", fake_mcp)
    monkeypatch.setenv("RETAILIQ_WORKFLOW_USE_MCP", "1")
    result = submit(api, "week2").json()
    assert result["status"] == "completed"
    assert calls == ["EL-003"]
    assert "Real stdio MCP inventory tool" in result["events"][1]["detail"]


def test_scope_guard_filters_simulated_analyst_rows(client):
    api, _ = client
    analyst = submit(api, "week3", role="analyst").json()
    manager = submit(api, "week3", role="manager").json()
    assert "ST-HCM only" in analyst["events"][1]["detail"]
    assert "1 permitted locations" in analyst["events"][2]["detail"]
    assert "all locations" in manager["events"][1]["detail"]
    assert "3 permitted locations" in manager["events"][2]["detail"]


def test_semantic_contract_includes_all_freshness_tiers(client):
    api, _ = client
    response = api.get("/api/workflows/semantics")
    assert response.status_code == 200
    contract = response.json()
    assert set(contract["freshness_tiers"]) == {"live", "15_min", "hourly", "daily"}
    assert not any(t["guaranteed"] for t in contract["freshness_tiers"].values())
    assert contract["metrics"]["net_revenue"]["unit"] == "VND"


def test_approval_report_reflects_final_state(client):
    api, _ = client
    run = submit(api, "week4").json()
    reviewed = api.post("/api/workflows/runs/" + run["id"] + "/review",
                        json={"role": "manager", "decision": "approve"}).json()
    assert reviewed["status"] == "approved_simulated"
    assert "Manager decision: approved_simulated" in reviewed["report"]
    assert "review pending" not in reviewed["report"]
    assert reviewed["events"][-1]["from"] == "manager_approval"


def test_week4_verification_replans_split_stock_once(client):
    api, data = client
    with sqlite3.connect(data) as db:
        db.execute("UPDATE inventory SET on_hand=reserved+8 WHERE sku='EL-003'")
    run = submit(api, "week4", quantity=20).json()
    assert run["status"] == "pending_manager"
    checks = [e for e in run["events"] if e["node"] == "verification"]
    assert [e["status"] for e in checks] == ["running", "completed"]
    assert "replan" in checks[0]["detail"]
    assert "allocation " in run["report"]
    assert any(e["from"] == "verification" and
               e["node"] == "fulfilment_optimisation_agent" for e in run["events"])
    assert any(e["from"] == "fulfilment_optimisation_agent" and
               e["node"] == "order_management_agent" for e in run["events"])
    graph = run["graph"]
    assert {"from":"verification","to":"fulfilment_optimisation_agent",
            "label":"retry"} in graph["edges"]


def test_week1_preview_reports_real_sql_not_live_langgraph(client):
    api, _ = client
    run = submit(api, "week1").json()
    assert run["status"] == "completed"
    assert "Deterministic preview, not live LangGraph" in run["report"]
    assert [e["node"] for e in run["events"]] == [
        "request", "router", "sales_agent", "sql_tool", "evidence", "answer"]
