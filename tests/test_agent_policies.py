"""Tests for agent policy enforcement and session clamping."""

from __future__ import annotations

import pytest

from engram import Engram


@pytest.fixture
def memory():
    eng = Engram(in_memory=True, provider="mock")
    return eng._memory


def test_exact_agent_policy_clamps_session_grants(memory):
    memory.upsert_agent_policy(
        user_id="u-policy",
        agent_id="planner",
        allowed_confidentiality_scopes=["work", "personal"],
        allowed_capabilities=["search", "propose_write"],
        allowed_namespaces=["default", "workbench"],
    )

    session = memory.create_session(
        user_id="u-policy",
        agent_id="planner",
        allowed_confidentiality_scopes=["work", "finance"],
        capabilities=["search", "review_commits"],
        namespaces=["default", "private-lab"],
    )

    assert set(session["allowed_confidentiality_scopes"]) == {"work"}
    assert set(session["capabilities"]) == {"search"}
    assert set(session["namespaces"]) == {"default"}


def test_wildcard_policy_applies_when_exact_missing(memory):
    memory.upsert_agent_policy(
        user_id="u-policy-wild",
        agent_id="*",
        allowed_confidentiality_scopes=["personal"],
        allowed_capabilities=["search"],
        allowed_namespaces=["default"],
    )

    session = memory.create_session(
        user_id="u-policy-wild",
        agent_id="new-agent",
        allowed_confidentiality_scopes=["personal", "work"],
        capabilities=["search", "propose_write"],
        namespaces=["default", "secret"],
    )

    assert set(session["allowed_confidentiality_scopes"]) == {"personal"}
    assert set(session["capabilities"]) == {"search"}
    assert set(session["namespaces"]) == {"default"}


def test_require_agent_policy_blocks_unknown_agent(monkeypatch, memory):
    monkeypatch.setenv("ENGRAM_V2_REQUIRE_AGENT_POLICY", "true")
    with pytest.raises(PermissionError, match="No agent policy configured"):
        memory.create_session(
            user_id="u-policy-strict",
            agent_id="unregistered-agent",
        )


def test_require_agent_policy_does_not_block_local_user_session(monkeypatch, memory):
    monkeypatch.setenv("ENGRAM_V2_REQUIRE_AGENT_POLICY", "true")
    session = memory.create_session(user_id="u-policy-strict", agent_id=None)
    assert session["token"]
