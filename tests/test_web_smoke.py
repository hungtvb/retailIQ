"""Regression coverage for local UI and API entrypoint (offline mode)."""
import pytest
from fastapi.testclient import TestClient
from retailiq.api import app

@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("RETAILIQ_MODE", "offline")
    return TestClient(app)

def test_homepage_served(client):
    response=client.get("/")
    assert response.status_code == 200
    assert "RetailIQ" in response.text

def test_health(client):
    response=client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"

@pytest.mark.parametrize("question,intent",[
    ("How many units of AlphaBook Pro 14 are in stock?", "stock"),
    ("What is the revenue this month?", "revenue"),
    ("Which products are top sellers?", "top"),
    ("Tell me about USB-C GaN Charger 65W", "product"),
])
def test_demo_asks(client, question, intent):
    response = client.post("/ask", json={"question": question})
    assert response.status_code == 200
    payload=response.json()
    assert payload["intent"] == intent
    assert payload["answer"]
    assert payload["mode"].startswith("OFFLINE")

def test_invalid_question(client):
    response=client.post("/ask",json={"question":"hi"})
    assert response.status_code==422
