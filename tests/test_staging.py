"""Tests for v2 staged writes, approval/rejection, and conflict stash."""

import pytest

from engram import Engram


@pytest.fixture
def memory():
    eng = Engram(in_memory=True, provider="mock")
    return eng._memory


def test_staging_commit_lifecycle(memory):
    session = memory.create_session(user_id="u-staging", agent_id="planner")

    proposal = memory.propose_write(
        content="Project codename is Atlas",
        user_id="u-staging",
        agent_id="planner",
        token=session["token"],
        mode="staging",
        infer=False,
    )
    assert proposal["commit_id"]
    assert proposal["status"] in {"PENDING", "AUTO_STASHED"}

    pending = memory.list_pending_commits(user_id="u-staging", status="PENDING")
    assert pending["count"] >= 1

    approved = memory.approve_commit(proposal["commit_id"])
    assert approved["status"] == "APPROVED"

    results = memory.search(
        query="Atlas codename",
        user_id="u-staging",
        agent_id="planner",
        limit=5,
    )
    assert results["results"]


def test_reject_commit(memory):
    session = memory.create_session(user_id="u-reject", agent_id="planner")

    proposal = memory.propose_write(
        content="Temporary wrong statement",
        user_id="u-reject",
        agent_id="planner",
        token=session["token"],
        mode="staging",
        infer=False,
    )

    rejected = memory.reject_commit(proposal["commit_id"], reason="Incorrect")
    assert rejected["status"] == "REJECTED"


def test_invariant_conflict_creates_stash(memory):
    session = memory.create_session(user_id="u-inv", agent_id="planner")

    initial = memory.propose_write(
        content="my name is Alice",
        user_id="u-inv",
        agent_id="planner",
        token=session["token"],
        mode="staging",
        infer=False,
    )
    memory.approve_commit(initial["commit_id"])

    conflicting = memory.propose_write(
        content="my name is Bob",
        user_id="u-inv",
        agent_id="planner",
        token=session["token"],
        mode="staging",
        infer=False,
    )

    assert conflicting["status"] == "AUTO_STASHED"
    stash_items = memory.db.list_conflict_stash(user_id="u-inv", resolution="UNRESOLVED", limit=20)
    assert stash_items
    assert stash_items[0]["conflict_key"] == "identity.name"


def test_commit_listing_requires_review_capability_for_agents(memory):
    writer = memory.create_session(
        user_id="u-review",
        agent_id="planner",
        capabilities=["propose_write"],
    )
    proposal = memory.propose_write(
        content="Pending proposal for review authorization check",
        user_id="u-review",
        agent_id="planner",
        token=writer["token"],
        mode="staging",
        infer=False,
    )
    assert proposal["commit_id"]

    with pytest.raises(PermissionError):
        memory.list_pending_commits(user_id="u-review", agent_id="planner", token=None, limit=10)
    with pytest.raises(PermissionError):
        memory.list_pending_commits(user_id="u-review", agent_id="planner", token=writer["token"], limit=10)

    reviewer = memory.create_session(
        user_id="u-review",
        agent_id="planner",
        capabilities=["review_commits"],
    )
    listed = memory.list_pending_commits(
        user_id="u-review",
        agent_id="planner",
        token=reviewer["token"],
        limit=10,
    )
    assert listed["count"] >= 1


def test_approve_commit_is_idempotent(memory):
    session = memory.create_session(user_id="u-idempotent", agent_id="planner")
    proposal = memory.propose_write(
        content="Idempotent approval memory",
        user_id="u-idempotent",
        agent_id="planner",
        token=session["token"],
        mode="staging",
        infer=False,
    )

    first = memory.approve_commit(proposal["commit_id"])
    assert first["status"] == "APPROVED"

    count_after_first = len(memory.db.get_all_memories(user_id="u-idempotent"))
    second = memory.approve_commit(proposal["commit_id"])
    count_after_second = len(memory.db.get_all_memories(user_id="u-idempotent"))

    assert second["status"] == "APPROVED"
    assert second["applied"] == []
    assert count_after_second == count_after_first


def test_direct_write_is_idempotent_by_source_event_id(memory):
    session = memory.create_session(user_id="u-source-event-direct", agent_id="planner")

    first = memory.propose_write(
        content="Source event idempotency payload",
        user_id="u-source-event-direct",
        agent_id="planner",
        token=session["token"],
        mode="direct",
        trusted_direct=True,
        infer=False,
        source_event_id="evt-direct-1",
        source_app="pytest",
    )
    second = memory.propose_write(
        content="Source event idempotency payload",
        user_id="u-source-event-direct",
        agent_id="planner",
        token=session["token"],
        mode="direct",
        trusted_direct=True,
        infer=False,
        source_event_id="evt-direct-1",
        source_app="pytest",
    )

    assert first["mode"] == "direct"
    assert second["mode"] == "direct"
    assert second["result"]["idempotent"] is True
    assert len(memory.db.get_all_memories(user_id="u-source-event-direct")) == 1


def test_approved_retries_do_not_duplicate_memory_when_source_event_matches(memory):
    session = memory.create_session(user_id="u-source-event-staging", agent_id="planner")

    first = memory.propose_write(
        content="Retry-safe staged payload",
        user_id="u-source-event-staging",
        agent_id="planner",
        token=session["token"],
        mode="staging",
        infer=False,
        source_event_id="evt-staging-1",
    )
    assert memory.approve_commit(first["commit_id"])["status"] == "APPROVED"

    second = memory.propose_write(
        content="Retry-safe staged payload",
        user_id="u-source-event-staging",
        agent_id="planner",
        token=session["token"],
        mode="staging",
        infer=False,
        source_event_id="evt-staging-1",
    )
    approved = memory.approve_commit(second["commit_id"])

    assert approved["status"] == "APPROVED"
    assert len(memory.db.get_all_memories(user_id="u-source-event-staging")) == 1


def test_failed_commit_apply_rolls_back_added_memories(monkeypatch, memory):
    commit = memory.kernel.staging_store.create_commit(
        user_id="u-atomic",
        agent_id="planner",
        scope="work",
        checks={"invariants_ok": True, "conflicts": [], "risk_score": 0.2},
        preview={},
        provenance={"source_type": "test"},
        changes=[
            {
                "op": "ADD",
                "target": "memory_item",
                "patch": {"content": "First staged memory", "metadata": {"namespace": "default"}},
            },
            {
                "op": "ADD",
                "target": "memory_item",
                "patch": {"content": "Second staged memory", "metadata": {"namespace": "default"}},
            },
        ],
    )

    original_apply = memory.kernel._apply_direct_write
    call_count = {"n": 0}

    def flaky_apply(**kwargs):
        call_count["n"] += 1
        if call_count["n"] == 2:
            raise RuntimeError("forced apply failure")
        return original_apply(**kwargs)

    monkeypatch.setattr(memory.kernel, "_apply_direct_write", flaky_apply)

    outcome = memory.approve_commit(commit["id"])
    assert outcome["error"] == "Commit apply failed"
    assert outcome["rolled_back"] >= 1

    all_memories = memory.db.get_all_memories(user_id="u-atomic")
    assert all_memories == []

    stored_commit = memory.kernel.staging_store.get_commit(commit["id"])
    assert stored_commit["status"] == "PENDING"
    assert "apply_error" in stored_commit["checks"]


def test_write_quota_per_agent_blocks_excess_proposals(monkeypatch, memory):
    monkeypatch.setenv("ENGRAM_V2_POLICY_WRITE_QUOTA_PER_AGENT_PER_HOUR", "1")
    session = memory.create_session(user_id="u-quota-agent", agent_id="planner")

    first = memory.propose_write(
        content="first quota proposal",
        user_id="u-quota-agent",
        agent_id="planner",
        token=session["token"],
        mode="staging",
        infer=False,
    )
    assert first["commit_id"]

    with pytest.raises(PermissionError, match="per-agent hourly"):
        memory.propose_write(
            content="second quota proposal",
            user_id="u-quota-agent",
            agent_id="planner",
            token=session["token"],
            mode="staging",
            infer=False,
        )


def test_write_quota_per_user_applies_across_agents(monkeypatch, memory):
    monkeypatch.setenv("ENGRAM_V2_POLICY_WRITE_QUOTA_PER_USER_PER_HOUR", "1")
    planner = memory.create_session(user_id="u-quota-user", agent_id="planner")
    codex = memory.create_session(user_id="u-quota-user", agent_id="codex")

    first = memory.propose_write(
        content="first user quota proposal",
        user_id="u-quota-user",
        agent_id="planner",
        token=planner["token"],
        mode="staging",
        infer=False,
    )
    assert first["commit_id"]

    with pytest.raises(PermissionError, match="per-user hourly"):
        memory.propose_write(
            content="second user quota proposal",
            user_id="u-quota-user",
            agent_id="codex",
            token=codex["token"],
            mode="staging",
            infer=False,
        )
