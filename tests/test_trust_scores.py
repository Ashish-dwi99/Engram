"""Tests for agent trust scoring and auto-merge behavior."""

from __future__ import annotations

import pytest

from engram import Engram


@pytest.fixture
def memory():
    eng = Engram(in_memory=True, provider="mock")
    return eng._memory


def test_agent_trust_updates_on_approve_and_reject(memory):
    session = memory.create_session(
        user_id="u-trust",
        agent_id="writer",
        capabilities=["propose_write", "review_commits"],
        namespaces=["default"],
    )

    first = memory.propose_write(
        content="First trust candidate memory",
        user_id="u-trust",
        agent_id="writer",
        token=session["token"],
        mode="staging",
        namespace="default",
        infer=False,
    )
    memory.approve_commit(first["commit_id"])

    trust_after_approve = memory.get_agent_trust(user_id="u-trust", agent_id="writer")
    assert trust_after_approve["total_proposals"] == 1
    assert trust_after_approve["approved_proposals"] == 1
    assert float(trust_after_approve["trust_score"]) > 0.9

    second = memory.propose_write(
        content="Second trust candidate memory",
        user_id="u-trust",
        agent_id="writer",
        token=session["token"],
        mode="staging",
        namespace="default",
        infer=False,
    )
    memory.reject_commit(second["commit_id"], reason="not needed")

    trust_after_reject = memory.get_agent_trust(user_id="u-trust", agent_id="writer")
    assert trust_after_reject["total_proposals"] == 2
    assert trust_after_reject["approved_proposals"] == 1
    assert trust_after_reject["rejected_proposals"] == 1
    assert 0.4 <= float(trust_after_reject["trust_score"]) < 1.0


def test_high_trust_agent_can_auto_merge(monkeypatch, memory):
    monkeypatch.setenv("ENGRAM_V2_TRUST_AUTOMERGE", "true")
    monkeypatch.setenv("ENGRAM_V2_AUTO_MERGE_TRUST_THRESHOLD", "0.6")
    monkeypatch.setenv("ENGRAM_V2_AUTO_MERGE_MIN_TOTAL", "1")
    monkeypatch.setenv("ENGRAM_V2_AUTO_MERGE_MIN_APPROVED", "1")
    monkeypatch.setenv("ENGRAM_V2_AUTO_MERGE_MAX_REJECT_RATE", "1.0")

    session = memory.create_session(
        user_id="u-automerge",
        agent_id="planner",
        capabilities=["propose_write", "review_commits"],
        namespaces=["default"],
    )

    baseline = memory.propose_write(
        content="Baseline memory to build trust",
        user_id="u-automerge",
        agent_id="planner",
        token=session["token"],
        mode="staging",
        namespace="default",
        infer=False,
    )
    memory.approve_commit(baseline["commit_id"])

    auto = memory.propose_write(
        content="This write should auto-merge",
        user_id="u-automerge",
        agent_id="planner",
        token=session["token"],
        mode="staging",
        namespace="default",
        infer=False,
    )
    assert auto["status"] == "APPROVED"
    assert auto.get("auto_merged") is True


def test_auto_merge_guardrails_block_low_evidence(monkeypatch, memory):
    monkeypatch.setenv("ENGRAM_V2_TRUST_AUTOMERGE", "true")
    monkeypatch.setenv("ENGRAM_V2_AUTO_MERGE_TRUST_THRESHOLD", "0.5")
    monkeypatch.delenv("ENGRAM_V2_AUTO_MERGE_MIN_TOTAL", raising=False)
    monkeypatch.delenv("ENGRAM_V2_AUTO_MERGE_MIN_APPROVED", raising=False)
    monkeypatch.delenv("ENGRAM_V2_AUTO_MERGE_MAX_REJECT_RATE", raising=False)

    session = memory.create_session(
        user_id="u-guard",
        agent_id="planner",
        capabilities=["propose_write", "review_commits"],
        namespaces=["default"],
    )

    baseline = memory.propose_write(
        content="Baseline trust seed for guardrails",
        user_id="u-guard",
        agent_id="planner",
        token=session["token"],
        mode="staging",
        namespace="default",
        infer=False,
    )
    memory.approve_commit(baseline["commit_id"])

    guarded = memory.propose_write(
        content="Should stay pending because evidence is too low",
        user_id="u-guard",
        agent_id="planner",
        token=session["token"],
        mode="staging",
        namespace="default",
        infer=False,
    )
    assert guarded["status"] == "PENDING"
    assert guarded.get("auto_merged") is False
