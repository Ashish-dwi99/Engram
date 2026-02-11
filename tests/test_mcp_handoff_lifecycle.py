"""MCP lifecycle tests for automatic handoff continuity."""

from __future__ import annotations

import asyncio
import time

import pytest

pytest.importorskip("mcp")

from engram import Engram
import engram.mcp_server as mcp_server


class _FakeHandoffBackend:
    def __init__(self):
        self.resume_calls = []
        self.checkpoint_calls = []

    def auto_resume_context(self, **kwargs):
        self.resume_calls.append(kwargs)
        return {
            "lane_id": "lane-1",
            "repo_id": "repo-1",
            "task_summary": "Resume packet",
        }

    def auto_checkpoint(self, **kwargs):
        self.checkpoint_calls.append(kwargs)
        return {
            "lane_id": kwargs.get("lane_id") or "lane-1",
            "checkpoint_id": f"cp-{len(self.checkpoint_calls)}",
            "status": kwargs.get("payload", {}).get("status", "active"),
            "version": len(self.checkpoint_calls),
        }

    def save_session_digest(self, **kwargs):  # pragma: no cover - interface completeness
        return {"id": "session-1", **kwargs}

    def get_last_session(self, **kwargs):  # pragma: no cover - interface completeness
        return {"id": "session-1", **kwargs}

    def list_sessions(self, **kwargs):  # pragma: no cover - interface completeness
        return []


@pytest.fixture(autouse=True)
def reset_state():
    mcp_server._lifecycle_state.clear()
    mcp_server._handoff_backend = None
    yield
    mcp_server._lifecycle_state.clear()
    mcp_server._handoff_backend = None


def test_auto_resume_and_tool_complete_checkpoint(monkeypatch):
    eng = Engram(in_memory=True, provider="mock")
    backend = _FakeHandoffBackend()
    monkeypatch.setattr(mcp_server, "get_memory", lambda: eng._memory)
    monkeypatch.setattr(mcp_server, "get_handoff_backend", lambda _memory: backend)

    output = asyncio.run(
        mcp_server.call_tool(
            "search_memory",
            {
                "query": "continuity",
                "user_id": "u-mcp-life-1",
                "requester_agent_id": "codex",
                "repo_path": "/tmp/repo",
            },
        )
    )
    assert output
    assert backend.resume_calls
    assert any(call.get("event_type") == "tool_complete" for call in backend.checkpoint_calls)


def test_idle_pause_checkpoint_and_shutdown_end_checkpoint(monkeypatch):
    eng = Engram(in_memory=True, provider="mock")
    backend = _FakeHandoffBackend()
    monkeypatch.setattr(mcp_server, "get_memory", lambda: eng._memory)
    monkeypatch.setattr(mcp_server, "get_handoff_backend", lambda _memory: backend)
    monkeypatch.setattr(mcp_server, "_idle_pause_seconds", 1)

    key = mcp_server._handoff_key(
        user_id="u-mcp-life-2",
        agent_id="codex",
        namespace="default",
        repo_id=None,
        repo_path="/tmp/repo",
    )
    mcp_server._lifecycle_state[key] = {
        "user_id": "u-mcp-life-2",
        "agent_id": "codex",
        "namespace": "default",
        "repo_path": "/tmp/repo",
        "lane_id": "lane-stale",
        "lane_type": "general",
        "objective": "Resume previous work",
        "confidentiality_scope": "work",
        "last_activity_ts": time.time() - 120,
    }

    asyncio.run(
        mcp_server.call_tool(
            "search_memory",
            {
                "query": "resume",
                "user_id": "u-mcp-life-2",
                "requester_agent_id": "codex",
                "repo_path": "/tmp/repo",
            },
        )
    )

    events = [call.get("event_type") for call in backend.checkpoint_calls]
    assert "agent_pause" in events
    assert "tool_complete" in events

    mcp_server._flush_agent_end_checkpoints()
    events = [call.get("event_type") for call in backend.checkpoint_calls]
    assert "agent_end" in events
