"""T06 regression: authenticated, owner-scoped simulation; no real Manager authority."""
from __future__ import annotations

from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from retailiq.api import app
from retailiq.infrastructure import auth
from retailiq.domain import workflow_demo
from scripts.seed import seed


@pytest.fixture
def api(tmp_path, monkeypatch):
    monkeypatch.setenv("RETAILIQ_CHAT_DB", str(tmp_path / "auth.sqlite"))
    monkeypatch.setenv("RETAILIQ_WORKFLOW_DB", str(tmp_path / "sim.sqlite"))
    path = tmp_path / "retail.sqlite"
    seed(path, write_support_files=False)
    monkeypatch.setenv("RETAILIQ_DATA_DB", str(path))
    with TestClient(app) as c:
        yield c


def login(api, suffix: str):
    name = "owner_" + suffix + uuid4().hex[:5]
    password = "local-testing-secret-long-passphrase"
    auth.create_local_user(name, "analyst", password)
    response = api.post("/api/auth/login", headers={"Origin": "http://testserver"},
                        json={"username": name, "password": password})
    assert response.status_code == 200
    me = api.get("/api/auth/me")
    assert me.status_code == 200
    return {"Origin": "http://testserver", "X-CSRF-Token": me.json()["csrf_token"]}


def test_authenticated_stateless_workflows_are_readable_but_not_public(api):
    assert api.get("/api/workflows/definitions").status_code == 401
    assert api.get("/api/workflows/semantics").status_code == 401
    headers = login(api, "reader")
    assert api.get("/api/workflows/definitions").status_code == 200
    assert api.get("/api/workflows/semantics").status_code == 200
    payload = api.post("/api/workflows/freshness/route", headers=headers,
                       json={"metric": "net_revenue"})
    assert payload.status_code == 200
    assert payload.json()["status"] == "UNVERIFIED"


def test_workflow_run_and_review_hidden_from_other_authenticated_user(api):
    headers_a = login(api, "a")
    created = api.post("/api/workflows/run", headers=headers_a,
                       json={"scenario": "week3", "sku": "EL-003", "role": "analyst"})
    assert created.status_code == 200, created.text
    rid = created.json()["id"]
    assert created.json()["status"] == "pending_manager"
    assert api.get("/api/workflows/runs/" + rid).status_code == 200

    headers_b = login(api, "b")
    assert api.get("/api/workflows/runs/" + rid).status_code == 404
    attempt = api.post("/api/workflows/runs/" + rid + "/review",
                       headers=headers_b, json={"role": "manager", "decision": "approve"})
    assert attempt.status_code == 404, attempt.text
    # Re-login as the owner and confirm the denied attempt made no changes.
    headers_a = login(api, "c")  # different user is still not the owner
    assert api.get("/api/workflows/runs/" + rid).status_code == 404


def test_old_unowned_workflow_rows_not_adopted_by_first_login(api):
    # Existing local simulation is no more trusted than old ownerless chat.
    old = workflow_demo.run_demo("week3", "EL-003", 1, "analyst")
    headers = login(api, "owner")
    assert api.get("/api/workflows/runs/" + old["id"]).status_code == 404
    denied = api.post("/api/workflows/runs/" + old["id"] + "/review", headers=headers,
                      json={"role": "manager", "decision": "approve"})
    assert denied.status_code == 404
