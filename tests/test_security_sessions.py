"""Security-focused API tests for session issuance and token enforcement."""

from __future__ import annotations

import importlib

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient

api_app_module = importlib.import_module("engram.api.app")
import engram.api.auth as auth_module
from engram import Engram


@pytest.fixture
def client():
    eng = Engram(in_memory=True, provider="mock")
    api_app_module._memory = eng._memory
    with TestClient(api_app_module.app) as test_client:
        yield test_client
    api_app_module._memory = None


def test_session_creation_requires_admin_key_when_configured(client, monkeypatch):
    monkeypatch.setenv("ENGRAM_ADMIN_KEY", "super-secret")

    denied = client.post(
        "/v1/sessions",
        json={"user_id": "u-admin", "agent_id": "agent-admin"},
    )
    assert denied.status_code == 403

    allowed = client.post(
        "/v1/sessions",
        headers={"X-Engram-Admin-Key": "super-secret"},
        json={"user_id": "u-admin", "agent_id": "agent-admin"},
    )
    assert allowed.status_code == 200
    body = allowed.json()
    assert body.get("token")
    assert body.get("session_id")


def test_untrusted_client_must_send_bearer_token(client, monkeypatch):
    # Simulate a non-local caller regardless of testclient host.
    monkeypatch.setattr(auth_module, "is_trusted_local_client", lambda request: False)

    memory = api_app_module.get_memory()
    memory.add(messages="Searchable memory for token test", user_id="u-token", infer=False)

    denied = client.post(
        "/v1/search",
        json={"query": "searchable", "user_id": "u-token", "agent_id": "agent-token"},
    )
    assert denied.status_code == 401

    session = api_app_module.get_kernel().create_session(
        user_id="u-token",
        agent_id="agent-token",
        capabilities=["search"],
    )
    allowed = client.post(
        "/v1/search",
        headers={"Authorization": f"Bearer {session['token']}"},
        json={"query": "searchable", "user_id": "u-token", "agent_id": "agent-token"},
    )
    assert allowed.status_code == 200
    payload = allowed.json()
    assert payload["count"] >= 1


def test_session_creation_returns_403_when_policy_required_and_missing(client, monkeypatch):
    monkeypatch.setenv("ENGRAM_V2_REQUIRE_AGENT_POLICY", "true")

    denied = client.post(
        "/v1/sessions",
        json={"user_id": "u-policy", "agent_id": "agent-missing"},
    )
    assert denied.status_code == 403
    assert "policy" in denied.json().get("detail", "").lower()


def test_handoff_session_creation_denies_untrusted_agent(client):
    denied = client.post(
        "/v1/sessions",
        json={
            "user_id": "u-handoff-policy",
            "agent_id": "rogue-agent",
            "capabilities": ["read_handoff"],
        },
    )
    assert denied.status_code == 403
    assert "handoff" in denied.json().get("detail", "").lower()

    trusted_without_policy = client.post(
        "/v1/sessions",
        json={
            "user_id": "u-handoff-policy",
            "agent_id": "codex",
            "capabilities": ["read_handoff", "write_handoff"],
        },
    )
    assert trusted_without_policy.status_code == 403

    policy = client.post(
        "/v1/agent-policies",
        json={
            "user_id": "u-handoff-policy",
            "agent_id": "codex",
            "allowed_confidentiality_scopes": ["work"],
            "allowed_capabilities": ["read_handoff", "write_handoff"],
            "allowed_namespaces": ["default"],
        },
    )
    assert policy.status_code == 200

    allowed = client.post(
        "/v1/sessions",
        json={
            "user_id": "u-handoff-policy",
            "agent_id": "codex",
            "capabilities": ["read_handoff", "write_handoff"],
        },
    )
    assert allowed.status_code == 200
    payload = allowed.json()
    assert {"read_handoff", "write_handoff"}.issubset(set(payload.get("capabilities", [])))


def test_agent_policy_api_round_trip_and_session_clamping(client):
    upsert = client.post(
        "/v1/agent-policies",
        json={
            "user_id": "u-policy-api",
            "agent_id": "planner",
            "allowed_confidentiality_scopes": ["work"],
            "allowed_capabilities": ["search"],
            "allowed_namespaces": ["default"],
        },
    )
    assert upsert.status_code == 200
    upsert_body = upsert.json()
    assert upsert_body["user_id"] == "u-policy-api"
    assert upsert_body["agent_id"] == "planner"

    session = client.post(
        "/v1/sessions",
        json={
            "user_id": "u-policy-api",
            "agent_id": "planner",
            "allowed_confidentiality_scopes": ["work", "finance"],
            "capabilities": ["search", "review_commits"],
            "namespaces": ["default", "private-lab"],
        },
    )
    assert session.status_code == 200
    session_body = session.json()
    assert set(session_body["allowed_confidentiality_scopes"]) == {"work"}
    assert set(session_body["capabilities"]) == {"search"}
    assert set(session_body["namespaces"]) == {"default"}

    get_one = client.get(
        "/v1/agent-policies",
        params={"user_id": "u-policy-api", "agent_id": "planner"},
    )
    assert get_one.status_code == 200
    payload = get_one.json()
    assert payload["policy"]["agent_id"] == "planner"

    delete = client.delete(
        "/v1/agent-policies",
        params={"user_id": "u-policy-api", "agent_id": "planner"},
    )
    assert delete.status_code == 200
    assert delete.json()["deleted"] is True


def test_handoff_endpoints_require_token_and_capabilities(client, monkeypatch):
    monkeypatch.setattr(auth_module, "is_trusted_local_client", lambda request: False)

    denied = client.post(
        "/v1/handoff/resume",
        json={"user_id": "u-handoff-api", "agent_id": "claude-code", "repo_path": "/tmp/repo"},
    )
    assert denied.status_code == 401

    api_app_module.get_kernel().db.upsert_agent_policy(
        user_id="u-handoff-api",
        agent_id="claude-code",
        allowed_confidentiality_scopes=["work"],
        allowed_capabilities=["read_handoff", "write_handoff"],
        allowed_namespaces=["default"],
    )
    session = api_app_module.get_kernel().create_session(
        user_id="u-handoff-api",
        agent_id="claude-code",
        capabilities=["read_handoff", "write_handoff"],
    )
    headers = {"Authorization": f"Bearer {session['token']}"}

    resumed = client.post(
        "/v1/handoff/resume",
        headers=headers,
        json={
            "user_id": "u-handoff-api",
            "agent_id": "claude-code",
            "repo_path": "/tmp/repo",
            "objective": "Continue backend work",
            "requester_agent_id": "claude-code",
        },
    )
    assert resumed.status_code == 200
    lane_id = resumed.json().get("lane_id")
    assert lane_id

    checkpoint = client.post(
        "/v1/handoff/checkpoint",
        headers=headers,
        json={
            "user_id": "u-handoff-api",
            "agent_id": "claude-code",
            "lane_id": lane_id,
            "repo_path": "/tmp/repo",
            "task_summary": "Implemented API endpoint",
            "event_type": "tool_complete",
            "requester_agent_id": "claude-code",
        },
    )
    assert checkpoint.status_code == 200
    assert checkpoint.json().get("checkpoint_id")

    lanes = client.get(
        "/v1/handoff/lanes",
        headers=headers,
        params={"user_id": "u-handoff-api", "requester_agent_id": "claude-code"},
    )
    assert lanes.status_code == 200
    assert lanes.json().get("count", 0) >= 1
