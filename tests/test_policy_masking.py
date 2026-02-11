"""Tests for confidentiality scope masking behavior."""

import pytest

from engram import Engram


@pytest.fixture
def memory():
    eng = Engram(in_memory=True, provider="mock")
    return eng._memory


def _stage_and_approve(memory, *, content, user_id, agent_id, token, scope):
    proposal = memory.propose_write(
        content=content,
        user_id=user_id,
        agent_id=agent_id,
        token=token,
        mode="staging",
        infer=False,
        scope=scope,
    )
    memory.approve_commit(proposal["commit_id"])


def test_out_of_scope_results_are_masked(memory):
    # Writer agent can write both work and finance memories.
    writer = memory.create_session(
        user_id="u-mask",
        agent_id="writer",
        allowed_confidentiality_scopes=["work", "finance"],
    )
    _stage_and_approve(
        memory,
        content="Work plan: migrate engram API endpoints",
        user_id="u-mask",
        agent_id="writer",
        token=writer["token"],
        scope="work",
    )
    _stage_and_approve(
        memory,
        content="Finance update: salary is 200k",
        user_id="u-mask",
        agent_id="writer",
        token=writer["token"],
        scope="finance",
    )

    # Reader session can only read work scope.
    reader = memory.create_session(
        user_id="u-mask",
        agent_id="reader",
        allowed_confidentiality_scopes=["work"],
    )

    payload = memory.search_with_context(
        query="salary and finance update",
        user_id="u-mask",
        agent_id="reader",
        token=reader["token"],
        limit=10,
    )

    assert payload["results"]
    assert any(item.get("masked") for item in payload["results"])
    masked_items = [item for item in payload["results"] if item.get("masked")]
    assert all(item.get("details") == "[REDACTED]" for item in masked_items)
    # Ensure secret value is not leaked in masked payload.
    for item in masked_items:
        assert "200k" not in str(item)
