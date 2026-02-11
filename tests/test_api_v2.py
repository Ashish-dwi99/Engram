"""Tests for Engram v2 session + token-gated search behavior."""

import pytest

from engram import Engram


@pytest.fixture
def memory():
    eng = Engram(in_memory=True, provider="mock")
    return eng._memory


def test_session_create_and_token_auth(memory):
    session = memory.create_session(
        user_id="u1",
        agent_id="agent-a",
        allowed_confidentiality_scopes=["work"],
        capabilities=["search", "propose_write"],
    )
    assert session["token"]
    assert session["session_id"]


def test_agent_search_requires_token(memory):
    with pytest.raises(PermissionError):
        memory.search_with_context(
            query="typescript",
            user_id="u1",
            agent_id="agent-a",
            token=None,
        )


def test_search_returns_context_packet(memory):
    session = memory.create_session(user_id="u1", agent_id="agent-a")

    staged = memory.propose_write(
        content="User prefers TypeScript for backend services",
        user_id="u1",
        agent_id="agent-a",
        token=session["token"],
        mode="staging",
        infer=False,
    )
    assert staged["status"] in {"PENDING", "AUTO_STASHED"}
    memory.approve_commit(staged["commit_id"])

    payload = memory.search_with_context(
        query="What backend language does the user prefer?",
        user_id="u1",
        agent_id="agent-a",
        token=session["token"],
        limit=5,
    )

    assert "results" in payload
    assert "context_packet" in payload
    assert payload["context_packet"]["snippets"]
    assert "retrieval_trace" in payload
    assert payload["retrieval_trace"]["strategy"] == "semantic_plus_episodic_intersection"


def test_non_agent_search_without_token_is_not_forced_masked(memory):
    memory.add(messages="User prefers Vim keybindings", user_id="u-local", infer=False)
    payload = memory.search_with_context(
        query="keybindings",
        user_id="u-local",
        agent_id=None,
        token=None,
        limit=5,
    )
    assert payload["results"]
    assert not all(item.get("masked") for item in payload["results"])


def test_capability_restrictions_are_enforced(memory):
    search_only = memory.create_session(
        user_id="u-cap",
        agent_id="agent-cap",
        capabilities=["search"],
    )
    with pytest.raises(PermissionError):
        memory.propose_write(
            content="Agent should not be able to write with search-only token",
            user_id="u-cap",
            agent_id="agent-cap",
            token=search_only["token"],
            mode="staging",
            infer=False,
        )

    write_only = memory.create_session(
        user_id="u-cap",
        agent_id="agent-cap",
        capabilities=["propose_write"],
    )
    with pytest.raises(PermissionError):
        memory.search_with_context(
            query="anything",
            user_id="u-cap",
            agent_id="agent-cap",
            token=write_only["token"],
            limit=3,
        )
