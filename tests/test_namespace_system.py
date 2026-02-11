"""Tests for namespace-aware access controls."""

from __future__ import annotations

import pytest

from engram import Engram


@pytest.fixture
def memory():
    eng = Engram(in_memory=True, provider="mock")
    return eng._memory


def _stage_and_approve(memory, *, content, user_id, agent_id, token, namespace):
    proposal = memory.propose_write(
        content=content,
        user_id=user_id,
        agent_id=agent_id,
        token=token,
        mode="staging",
        infer=False,
        scope="work",
        namespace=namespace,
    )
    memory.approve_commit(proposal["commit_id"])
    return proposal


def test_namespace_masking_for_reader(memory):
    memory.declare_namespace(user_id="u-ns", namespace="workbench")
    memory.declare_namespace(user_id="u-ns", namespace="private-lab")

    writer = memory.create_session(
        user_id="u-ns",
        agent_id="writer",
        namespaces=["workbench", "private-lab"],
    )
    _stage_and_approve(
        memory,
        content="Workbench note about architecture",
        user_id="u-ns",
        agent_id="writer",
        token=writer["token"],
        namespace="workbench",
    )
    _stage_and_approve(
        memory,
        content="Private-lab secret about salaries",
        user_id="u-ns",
        agent_id="writer",
        token=writer["token"],
        namespace="private-lab",
    )

    reader = memory.create_session(
        user_id="u-ns",
        agent_id="reader",
        namespaces=["workbench"],
    )
    payload = memory.search_with_context(
        query="architecture and salaries",
        user_id="u-ns",
        agent_id="reader",
        token=reader["token"],
        limit=10,
    )

    assert payload["results"]
    masked = [item for item in payload["results"] if item.get("masked")]
    visible = [item for item in payload["results"] if not item.get("masked")]
    assert masked
    assert visible
    assert all(item.get("details") == "[REDACTED]" for item in masked)
    assert all(item.get("namespace", "workbench") == "workbench" for item in visible)
