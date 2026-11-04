"""Ensure application honors .env bootstrap and full-mode LangGraph dispatch."""
from fastapi.testclient import TestClient
from tests.auth_client import signed_in_client
from retailiq.api import app
from retailiq import assistant
from retailiq import graph

def test_app_import_loads_dotenv_before_request():
    assert hasattr(assistant, "_provider_config")

def test_full_mode_dispatches_to_langgraph(monkeypatch, tmp_path):
    monkeypatch.setenv('RETAILIQ_CHAT_DB', str(tmp_path / 'chat.sqlite'))
    monkeypatch.setenv("RETAILIQ_MODE", "full")
    expected={"mode":"LangGraph + SQL / Chroma RAG","intent":"stock","answer":"Demo: 12 units", "records":[], "contexts":[]}
    monkeypatch.setattr(graph,"run",lambda question: {**expected,"question":question})
    with TestClient(app) as client:
        signed_in_client(app, client=client)
        response=client.post("/ask",json={"question":"How many units in stock?"})
    assert response.status_code==200
    assert response.json()["mode"]==expected["mode"]
