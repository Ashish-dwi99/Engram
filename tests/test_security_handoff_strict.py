"""Strict handoff security defaults tests."""

from __future__ import annotations

import pytest

from engram import Engram


@pytest.fixture
def memory():
    eng = Engram(in_memory=True, provider="mock")
    return eng._memory


def test_strict_default_denies_implicit_trusted_bootstrap(memory):
    with pytest.raises(PermissionError):
        memory.create_session(
            user_id="u-strict-1",
            agent_id="codex",
            capabilities=["read_handoff", "write_handoff"],
        )


def test_opt_in_bootstrap_allows_trusted_agent(memory):
    memory.handoff_config.allow_auto_trusted_bootstrap = True
    session = memory.create_session(
        user_id="u-strict-2",
        agent_id="codex",
        capabilities=["read_handoff", "write_handoff"],
    )
    assert session.get("token")
    assert {"read_handoff", "write_handoff"}.issubset(set(session.get("capabilities", [])))
