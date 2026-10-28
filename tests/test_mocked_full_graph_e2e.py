"""Mock-provider ASGI acceptance of ACTUAL compiled LangGraph.

Remote model and vector services are fakes; SQL, supervisor subgraph,
checkpoint persistence, routing and FastAPI endpoints execute real code.
Do not interpret as live provider/Chroma/LangSmith certification.
"""
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from retailiq.api import app
from retailiq import assistant
from retailiq.core import config
from retailiq.orchestration import week1_graph as graph


class FakeRouter:
    def with_structured_output(self, schema):
        return self

    def invoke(self, messages):
        return SimpleNamespace(intent=graph.classify(messages[-1][1]))


class FakeProductModel:
    def invoke(self, messages):
        return SimpleNamespace(content="USB-C GaN Charger 65W supports 65W USB-C charging [S1]")


@pytest.fixture
def mocked_full(monkeypatch, tmp_path):
    pytest.importorskip("langgraph")
    graph.close_checkpoint_graph()
    monkeypatch.setenv("RETAILIQ_MODE", "full")
    monkeypatch.setenv("RETAILIQ_SUPERVISOR_MODE", "deterministic")
    monkeypatch.setenv("RETAILIQ_CHAT_DB", str(tmp_path / "sessions.sqlite3"))
    monkeypatch.setenv("RETAILIQ_CHECKPOINT_DB", str(tmp_path / "checkpoints.sqlite3"))
    monkeypatch.setenv("RETAILIQ_LOG_FILE", str(tmp_path / "events.jsonl"))
    monkeypatch.setenv("LANGSMITH_TRACING", "false")
    monkeypatch.setattr(graph, "chat_model", lambda: FakeRouter())
    monkeypatch.setattr(config, "chat_model", lambda: FakeProductModel())
    monkeypatch.setattr(assistant, "retrieve", lambda question: [{
        "source": "data/product_docs/EL-003.md",
        "text": "USB-C GaN Charger 65W supports 65W USB-C PD charging.",
    }])
    try:
        with TestClient(app) as client:
            yield client
    finally:
        graph.close_checkpoint_graph()


def test_mocked_full_graph_all_five_business_routes(mocked_full):
    cases = [
        ("How many units of AlphaBook Pro 14 are in stock?", "stock", "inventory_agent"),
        ("What is revenue this month?", "revenue", "sales_agent"),
        ("Which products are top sellers?", "top", "sales_agent"),
        ("Tell me about USB-C GaN Charger 65W", "product", "product_agent"),
        ("Which top seller needs replenishment review based on stock?",
         "decision", "retail_supervisor"),
    ]
    for question, intent, agent in cases:
        response = mocked_full.post("/ask", json={"question": question})
        assert response.status_code == 200, (intent, response.text[:300])
        payload = response.json()
        assert payload["intent"] == intent
        assert payload["active_agent"] == agent
        assert payload["mode"].startswith("LangGraph")
        assert payload["answer"].strip()
        if intent == "product":
            assert "[S1]" in payload["answer"]
            assert payload["contexts"][0]["source"] == "data/product_docs/EL-003.md"
        if intent == "decision":
            assert payload["subagents"] == ["sales_agent", "inventory_agent"]
            assert payload["records"]


def test_mocked_full_graph_session_handoff_and_durable_checkpoint(mocked_full):
    sid = mocked_full.post("/api/sessions", json={}).json()["id"]
    for question, intent in [
        ("Which products are top sellers?", "top"),
        ("How many units of the top seller are in stock?", "stock"),
    ]:
        response = mocked_full.post("/ask", json={"question": question, "session_id": sid})
        assert response.status_code == 200, response.text[:300]
        assert response.json()["intent"] == intent
    stored = mocked_full.get("/api/sessions/" + sid).json()
    assert len(stored["messages"]) == 4
    assert stored["active_agent"] == "inventory_agent"
    from langgraph.checkpoint.sqlite import SqliteSaver
    assert graph._session_graph().get_state(
        {"configurable": {"thread_id": sid}}
    ).values["active_agent"] == "inventory_agent"


def test_model_failure_does_not_persist_a_partial_turn(mocked_full, monkeypatch):
    sid = mocked_full.post("/api/sessions", json={}).json()["id"]

    class ProviderDown:
        def invoke(self, messages):
            raise TimeoutError("simulated provider unavailable")

    monkeypatch.setattr(config, "chat_model", lambda: ProviderDown())
    response = mocked_full.post("/ask", json={
        "question": "Tell me about USB-C GaN Charger 65W", "session_id": sid})
    assert response.status_code == 503
    assert "simulated provider unavailable" not in response.text
    assert mocked_full.get("/api/sessions/" + sid).json()["messages"] == []
