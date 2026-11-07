"""Real HTTP auth for disposable local scenario runners; never an auth bypass."""
from __future__ import annotations

import os
from secrets import token_urlsafe
from uuid import uuid4

from retailiq.infrastructure import auth


def login_fixture_client(client):
    """Provision only under an explicitly isolated RETAILIQ_CHAT_DB path."""
    if not os.environ.get("RETAILIQ_CHAT_DB"):
        raise RuntimeError("An isolated RETAILIQ_CHAT_DB is required for scenario authentication")
    username = "scenario_" + uuid4().hex[:20]
    password = token_urlsafe(32)
    auth.create_local_user(username, "analyst", password)
    response = client.post(
        "/api/auth/login", headers={"Origin": "http://testserver"},
        json={"username": username, "password": password})
    if response.status_code != 200:
        raise RuntimeError("Scenario HTTP login failed")
    identity = client.get("/api/auth/me")
    if identity.status_code != 200:
        raise RuntimeError("Scenario CSRF bootstrap failed")
    client.headers.update({
        "Origin": "http://testserver",
        "X-CSRF-Token": identity.json()["csrf_token"],
    })
    return client
