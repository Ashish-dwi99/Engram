"""Compatibility API tests for legacy handoff session routes."""

from __future__ import annotations

import importlib

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient

from engram import Engram

api_app_module = importlib.import_module("engram.api.app")


@pytest.fixture
def client():
    eng = Engram(in_memory=True, provider="mock")
    api_app_module._memory = eng._memory
    with TestClient(api_app_module.app) as test_client:
        yield test_client
    api_app_module._memory = None


def _session_token(user_id: str, agent_id: str) -> str:
    kernel = api_app_module.get_kernel()
    kernel.db.upsert_agent_policy(
        user_id=user_id,
        agent_id=agent_id,
        allowed_confidentiality_scopes=["work"],
        allowed_capabilities=["read_handoff", "write_handoff"],
        allowed_namespaces=["default"],
    )
    session = kernel.create_session(
        user_id=user_id,
        agent_id=agent_id,
        capabilities=["read_handoff", "write_handoff"],
        namespaces=["default"],
    )
    return session["token"]


def test_handoff_session_compat_routes_round_trip(client):
    user_id = "u-handoff-api-compat"
    agent_id = "codex"
    token = _session_token(user_id=user_id, agent_id=agent_id)
    headers = {"Authorization": f"Bearer {token}"}

    digest = client.post(
        "/v1/handoff/sessions/digest",
        headers=headers,
        json={
            "user_id": user_id,
            "agent_id": agent_id,
            "requester_agent_id": agent_id,
            "task_summary": "Harden handoff compatibility routes",
            "repo": "/tmp/engram-repo",
            "status": "paused",
            "files_touched": ["engram/api/app.py"],
            "todos_remaining": ["Validate old MCP clients"],
        },
    )
    assert digest.status_code == 200
    digest_payload = digest.json()
    assert digest_payload.get("id")
    assert digest_payload.get("task_summary") == "Harden handoff compatibility routes"

    last = client.get(
        "/v1/handoff/sessions/last",
        headers=headers,
        params={
            "user_id": user_id,
            "agent_id": agent_id,
            "requester_agent_id": agent_id,
            "repo": "/tmp/engram-repo",
        },
    )
    assert last.status_code == 200
    last_payload = last.json()
    assert last_payload.get("task_summary") == "Harden handoff compatibility routes"
    assert last_payload.get("from_agent") == agent_id

    listed = client.get(
        "/v1/handoff/sessions",
        headers=headers,
        params={
            "user_id": user_id,
            "agent_id": agent_id,
            "requester_agent_id": agent_id,
            "repo": "/tmp/engram-repo",
            "limit": 10,
        },
    )
    assert listed.status_code == 200
    listed_payload = listed.json()
    assert listed_payload.get("count", 0) >= 1
    assert listed_payload["sessions"][0]["task_summary"]


def test_handoff_routes_reject_invalid_status_values(client):
    user_id = "u-handoff-api-compat-invalid"
    agent_id = "codex"
    token = _session_token(user_id=user_id, agent_id=agent_id)
    headers = {"Authorization": f"Bearer {token}"}

    invalid_last = client.get(
        "/v1/handoff/sessions/last",
        headers=headers,
        params={
            "user_id": user_id,
            "agent_id": agent_id,
            "requester_agent_id": agent_id,
            "statuses": "running",
        },
    )
    assert invalid_last.status_code == 422

    invalid_list = client.get(
        "/v1/handoff/sessions",
        headers=headers,
        params={
            "user_id": user_id,
            "agent_id": agent_id,
            "requester_agent_id": agent_id,
            "status": "running",
        },
    )
    assert invalid_list.status_code == 422
