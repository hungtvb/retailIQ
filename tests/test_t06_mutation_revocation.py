"""T06 security: revocation wins over later memory/session mutation writes."""
import pytest
from fastapi.testclient import TestClient

from retailiq.api import app
from retailiq.infrastructure import auth, sessions
from tests.auth_client import active_principal, signed_in_client


@pytest.fixture
def owned_session(tmp_path, monkeypatch):
    monkeypatch.setenv("RETAILIQ_CHAT_DB", str(tmp_path / "auth.sqlite"))
    with TestClient(app) as client:
        signed_in_client(app, client=client)
        sid = client.post("/api/sessions", json={}).json()["id"]
        yield client, sid, active_principal(client)


def test_revoked_before_memory_write_cannot_mutate(owned_session):
    client, sid, principal = owned_session
    auth.revoke_session(principal)
    with pytest.raises(PermissionError):
        sessions.save_customer_memory(
            sid, consent=True,
            preferences={"preferred_category": "Accessory"},
            owner_user_id=principal.user_id, principal=principal)
    assert sessions.get_customer_memory(
        sid, owner_user_id=principal.user_id)["consent"] is False


def test_revoked_before_conversation_delete_cannot_remove_history(owned_session):
    client, sid, principal = owned_session
    auth.revoke_session(principal)
    with pytest.raises(PermissionError):
        sessions.delete_session(sid, owner_user_id=principal.user_id,
                                principal=principal)
    assert sessions.get_session(sid, owner_user_id=principal.user_id) is not None


def test_other_owner_cannot_mutate_even_with_active_auth(owned_session):
    client, sid, first = owned_session
    signed_in_client(app, client=client)
    intruder = active_principal(client)
    with pytest.raises((KeyError, PermissionError)):
        sessions.save_customer_memory(
            sid, consent=True, preferences={"preferred_category": "Accessory"},
            owner_user_id=first.user_id, principal=intruder)
    with pytest.raises(PermissionError):
        sessions.delete_session(sid, owner_user_id=first.user_id,
                                principal=intruder)
    assert sessions.get_customer_memory(
        sid, owner_user_id=first.user_id)["consent"] is False
