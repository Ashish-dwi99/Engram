"""Hosted handoff backend routing tests."""

from __future__ import annotations

import asyncio

import pytest

pytest.importorskip("mcp")

from engram import Engram
from engram.core.handoff_backend import HostedHandoffBackend, create_handoff_backend
import engram.mcp_server as mcp_server


@pytest.fixture(autouse=True)
def reset_mcp_state():
    mcp_server._handoff_backend = None
    mcp_server._lifecycle_state.clear()
    yield
    mcp_server._handoff_backend = None
    mcp_server._lifecycle_state.clear()


def test_backend_prefers_hosted_when_api_url_is_set(monkeypatch):
    eng = Engram(in_memory=True, provider="mock")
    monkeypatch.setenv("ENGRAM_API_URL", "http://127.0.0.1:8100")
    backend = create_handoff_backend(eng._memory)
    assert isinstance(backend, HostedHandoffBackend)


def test_get_last_session_reports_hosted_backend_unavailable(monkeypatch):
    eng = Engram(in_memory=True, provider="mock")

    monkeypatch.setenv("ENGRAM_API_URL", "http://127.0.0.1:1")
    monkeypatch.setattr(mcp_server, "get_memory", lambda: eng._memory)

    output = asyncio.run(
        mcp_server.call_tool(
            "get_last_session",
            {
                "user_id": "u-hosted-err",
                "agent_id": "codex",
                "requester_agent_id": "codex",
                "repo": "/tmp/repo",
            },
        )
    )
    payload_text = output[0].text
    assert "hosted_backend_unavailable" in payload_text
