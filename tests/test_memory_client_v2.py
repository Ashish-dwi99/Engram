"""Tests for MemoryClient v2 policy-management helpers."""

from __future__ import annotations

import pytest

pytest.importorskip("requests")

from engram.memory.client import MemoryClient


def test_memory_client_agent_policy_methods(monkeypatch):
    calls = []

    def fake_request(self, method, path, *, params=None, json_body=None, extra_headers=None):
        calls.append(
            {
                "method": method,
                "path": path,
                "params": params,
                "json_body": json_body,
                "extra_headers": extra_headers,
            }
        )
        return {"ok": True}

    monkeypatch.setattr(MemoryClient, "_request", fake_request)

    client = MemoryClient(host="http://localhost:8100")

    client.upsert_agent_policy(
        user_id="u-client",
        agent_id="planner",
        allowed_confidentiality_scopes=["work", "personal"],
        allowed_capabilities=["search"],
        allowed_namespaces=["default", "workbench"],
    )
    assert calls[-1]["method"] == "POST"
    assert calls[-1]["path"] == "/v1/agent-policies"
    assert calls[-1]["json_body"]["agent_id"] == "planner"

    client.list_agent_policies(user_id="u-client")
    assert calls[-1]["method"] == "GET"
    assert calls[-1]["path"] == "/v1/agent-policies"
    assert calls[-1]["params"] == {"user_id": "u-client"}

    client.get_agent_policy(user_id="u-client", agent_id="planner", include_wildcard=False)
    assert calls[-1]["method"] == "GET"
    assert calls[-1]["path"] == "/v1/agent-policies"
    assert calls[-1]["params"]["agent_id"] == "planner"
    assert calls[-1]["params"]["include_wildcard"] == "false"

    client.delete_agent_policy(user_id="u-client", agent_id="planner")
    assert calls[-1]["method"] == "DELETE"
    assert calls[-1]["path"] == "/v1/agent-policies"
    assert calls[-1]["params"] == {"user_id": "u-client", "agent_id": "planner"}

    client.handoff_resume(user_id="u-client", agent_id="planner", repo_path="/tmp/repo")
    assert calls[-1]["method"] == "POST"
    assert calls[-1]["path"] == "/v1/handoff/resume"
    assert calls[-1]["json_body"]["agent_id"] == "planner"

    client.handoff_checkpoint(user_id="u-client", agent_id="planner", task_summary="Continue lane")
    assert calls[-1]["method"] == "POST"
    assert calls[-1]["path"] == "/v1/handoff/checkpoint"
    assert calls[-1]["json_body"]["task_summary"] == "Continue lane"

    client.list_handoff_lanes(user_id="u-client", limit=5)
    assert calls[-1]["method"] == "GET"
    assert calls[-1]["path"] == "/v1/handoff/lanes"
    assert calls[-1]["params"]["limit"] == 5
