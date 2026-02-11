"""Tests for cross-agent handoff session bus and legacy compatibility APIs."""

from __future__ import annotations

import os

import pytest

from engram import Engram


@pytest.fixture
def memory():
    eng = Engram(in_memory=True, provider="mock")
    return eng._memory


def _token(memory, *, user_id: str, agent_id: str, capabilities):
    if {"read_handoff", "write_handoff"} & set(capabilities):
        memory.db.upsert_agent_policy(
            user_id=user_id,
            agent_id=agent_id,
            allowed_confidentiality_scopes=["work"],
            allowed_capabilities=["read_handoff", "write_handoff"],
            allowed_namespaces=["default"],
        )
    session = memory.create_session(
        user_id=user_id,
        agent_id=agent_id,
        capabilities=list(capabilities),
    )
    return session["token"]


def test_save_and_get_last_session_roundtrip(memory, tmp_path):
    repo_path = str(tmp_path)
    alias_repo_path = os.path.join(repo_path, ".", "")
    token = _token(
        memory,
        user_id="u-handoff-1",
        agent_id="claude-code",
        capabilities=["read_handoff", "write_handoff"],
    )

    saved = memory.save_session_digest(
        "u-handoff-1",
        "claude-code",
        {
            "task_summary": "Implement auto lane routing",
            "repo": repo_path,
            "status": "paused",
            "decisions_made": ["Use git fingerprint repo_id"],
            "files_touched": ["engram/core/handoff_bus.py"],
            "todos_remaining": ["Add API tests"],
            "blockers": ["Need auth token propagation"],
            "key_commands": ["pytest tests/test_handoff.py -q"],
            "test_results": ["unit tests pending"],
            "context_snapshot": "Bus is mostly wired.",
        },
        token=token,
        requester_agent_id="claude-code",
    )
    assert saved["id"]
    assert saved["repo_id"]

    resumed = memory.get_last_session(
        "u-handoff-1",
        agent_id="claude-code",
        repo=alias_repo_path,
        token=token,
        requester_agent_id="claude-code",
    )
    assert resumed is not None
    assert resumed["task_summary"] == "Implement auto lane routing"
    assert resumed["from_agent"] == "claude-code"
    assert resumed["repo_id"] == saved["repo_id"]
    assert resumed["blockers"] == ["Need auth token propagation"]


def test_hard_prune_keeps_latest_session_order(memory, tmp_path):
    repo_path = str(tmp_path)
    memory.handoff_processor.session_bus.max_sessions_per_user = 2
    token = _token(
        memory,
        user_id="u-handoff-2",
        agent_id="claude-code",
        capabilities=["read_handoff", "write_handoff"],
    )

    for idx in range(4):
        memory.save_session_digest(
            "u-handoff-2",
            "claude-code",
            {
                "task_summary": f"session-{idx}",
                "repo": repo_path,
                "status": "paused",
            },
            token=token,
            requester_agent_id="claude-code",
        )

    sessions = memory.list_sessions(
        "u-handoff-2",
        repo=repo_path,
        limit=10,
        token=token,
        requester_agent_id="claude-code",
    )
    assert len(sessions) == 2

    resumed = memory.get_last_session(
        "u-handoff-2",
        repo=repo_path,
        token=token,
        requester_agent_id="claude-code",
    )
    assert resumed["task_summary"] == "session-3"


def test_auto_resume_cross_agent_lane_continuity(memory, tmp_path):
    repo_path = str(tmp_path)
    claude_token = _token(
        memory,
        user_id="u-handoff-3",
        agent_id="claude-code",
        capabilities=["read_handoff", "write_handoff"],
    )

    initial_resume = memory.auto_resume_context(
        user_id="u-handoff-3",
        agent_id="claude-code",
        repo_path=repo_path,
        objective="Build handoff APIs",
        token=claude_token,
        requester_agent_id="claude-code",
    )
    lane_id = initial_resume["lane_id"]
    assert initial_resume["created_new_lane"] is True

    checkpoint = memory.auto_checkpoint(
        user_id="u-handoff-3",
        agent_id="claude-code",
        repo_path=repo_path,
        lane_id=lane_id,
        payload={
            "task_summary": "Added handoff resume endpoint",
            "files_touched": ["engram/api/app.py"],
            "todos_remaining": ["Add lane listing endpoint tests"],
        },
        token=claude_token,
        requester_agent_id="claude-code",
    )
    assert checkpoint["checkpoint_id"]

    codex_token = _token(
        memory,
        user_id="u-handoff-3",
        agent_id="codex",
        capabilities=["read_handoff", "write_handoff"],
    )
    codex_resume = memory.auto_resume_context(
        user_id="u-handoff-3",
        agent_id="codex",
        repo_path=repo_path,
        objective="Continue previous work",
        token=codex_token,
        requester_agent_id="codex",
    )
    assert codex_resume["lane_id"] == lane_id
    assert codex_resume["task_summary"] == "Added handoff resume endpoint"
    assert "Add lane listing endpoint tests" in codex_resume["next_actions"]


def test_stale_expected_version_logs_conflict(memory, tmp_path):
    repo_path = str(tmp_path)
    token = _token(
        memory,
        user_id="u-handoff-4",
        agent_id="frontend",
        capabilities=["read_handoff", "write_handoff"],
    )
    resume = memory.auto_resume_context(
        user_id="u-handoff-4",
        agent_id="frontend",
        repo_path=repo_path,
        objective="Polish UI",
        token=token,
        requester_agent_id="frontend",
    )
    lane_id = resume["lane_id"]

    first = memory.auto_checkpoint(
        user_id="u-handoff-4",
        agent_id="frontend",
        lane_id=lane_id,
        repo_path=repo_path,
        payload={"task_summary": "Drafted UI wireframes"},
        expected_version=0,
        token=token,
        requester_agent_id="frontend",
    )
    assert first["checkpoint_id"]

    second = memory.auto_checkpoint(
        user_id="u-handoff-4",
        agent_id="frontend",
        lane_id=lane_id,
        repo_path=repo_path,
        payload={"task_summary": "Updated component hierarchy"},
        expected_version=0,  # stale on purpose
        token=token,
        requester_agent_id="frontend",
    )
    assert second["checkpoint_id"]
    assert len(second.get("conflicts", [])) == 1

    conflicts = memory.db.list_handoff_lane_conflicts(lane_id)
    assert conflicts
    assert "task_summary" in set(conflicts[0].get("conflict_fields", []))


def test_handoff_capabilities_are_enforced(memory, tmp_path):
    repo_path = str(tmp_path)
    with pytest.raises(PermissionError):
        memory.save_session_digest(
            "u-handoff-5",
            "backend",
            {"task_summary": "No token should fail", "repo": repo_path},
        )

    weak_token = _token(
        memory,
        user_id="u-handoff-5",
        agent_id="backend",
        capabilities=["search"],
    )
    with pytest.raises(PermissionError):
        memory.save_session_digest(
            "u-handoff-5",
            "backend",
            {"task_summary": "Wrong capability", "repo": repo_path},
            token=weak_token,
            requester_agent_id="backend",
        )

    strong_token = _token(
        memory,
        user_id="u-handoff-5",
        agent_id="backend",
        capabilities=["read_handoff", "write_handoff"],
    )
    saved = memory.save_session_digest(
        "u-handoff-5",
        "backend",
        {"task_summary": "Capability granted", "repo": repo_path},
        token=strong_token,
        requester_agent_id="backend",
    )
    assert saved["id"]


def test_get_last_session_falls_back_to_lane_checkpoint(memory, tmp_path):
    repo_path = str(tmp_path)
    token = _token(
        memory,
        user_id="u-handoff-6",
        agent_id="claude-code",
        capabilities=["read_handoff", "write_handoff"],
    )

    resume = memory.auto_resume_context(
        user_id="u-handoff-6",
        agent_id="claude-code",
        repo_path=repo_path,
        objective="Implement lane fallback",
        token=token,
        requester_agent_id="claude-code",
    )
    lane_id = resume["lane_id"]

    memory.auto_checkpoint(
        user_id="u-handoff-6",
        agent_id="claude-code",
        repo_path=repo_path,
        lane_id=lane_id,
        payload={
            "task_summary": "Checkpoint without legacy digest session",
            "files_touched": ["engram/core/handoff_bus.py"],
            "todos_remaining": ["Verify get_last_session fallback"],
        },
        token=token,
        requester_agent_id="claude-code",
    )

    # No save_session_digest call happened, so legacy session rows are absent.
    # get_last_session must still return continuity from lane/checkpoint state.
    resumed = memory.get_last_session(
        "u-handoff-6",
        repo=repo_path,
        token=token,
        requester_agent_id="claude-code",
    )
    assert resumed is not None
    assert resumed["lane_id"] == lane_id
    assert resumed["task_summary"] == "Checkpoint without legacy digest session"
    assert "Verify get_last_session fallback" in resumed["todos_remaining"]

    listed = memory.list_sessions(
        "u-handoff-6",
        repo=repo_path,
        token=token,
        requester_agent_id="claude-code",
    )
    assert listed
    assert listed[0]["lane_id"] == lane_id
    assert listed[0]["task_summary"] == "Checkpoint without legacy digest session"


def test_get_last_session_prefers_active_lane_over_completed_digest(memory, tmp_path):
    repo_path = str(tmp_path)
    token = _token(
        memory,
        user_id="u-handoff-7",
        agent_id="claude-code",
        capabilities=["read_handoff", "write_handoff"],
    )

    memory.save_session_digest(
        "u-handoff-7",
        "claude-code",
        {
            "task_summary": "Historical completed digest",
            "repo": repo_path,
            "status": "completed",
        },
        token=token,
        requester_agent_id="claude-code",
    )

    resume = memory.auto_resume_context(
        user_id="u-handoff-7",
        agent_id="claude-code",
        repo_path=repo_path,
        objective="Continue active work",
        token=token,
        requester_agent_id="claude-code",
    )
    lane_id = resume["lane_id"]
    memory.auto_checkpoint(
        user_id="u-handoff-7",
        agent_id="claude-code",
        repo_path=repo_path,
        lane_id=lane_id,
        payload={
            "task_summary": "Live lane checkpoint",
            "todos_remaining": ["finish active task"],
        },
        token=token,
        requester_agent_id="claude-code",
    )

    resumed = memory.get_last_session(
        "u-handoff-7",
        repo=repo_path,
        token=token,
        requester_agent_id="claude-code",
    )
    assert resumed is not None
    assert resumed["task_summary"] == "Live lane checkpoint"
    assert resumed["lane_id"] == lane_id
    assert resumed["status"] == "active"


def test_get_last_session_respects_explicit_status_filter(memory, tmp_path):
    repo_path = str(tmp_path)
    token = _token(
        memory,
        user_id="u-handoff-8",
        agent_id="claude-code",
        capabilities=["read_handoff", "write_handoff"],
    )

    memory.save_session_digest(
        "u-handoff-8",
        "claude-code",
        {
            "task_summary": "Completed digest only",
            "repo": repo_path,
            "status": "completed",
        },
        token=token,
        requester_agent_id="claude-code",
    )

    resume = memory.auto_resume_context(
        user_id="u-handoff-8",
        agent_id="claude-code",
        repo_path=repo_path,
        objective="Live branch",
        token=token,
        requester_agent_id="claude-code",
    )
    lane_id = resume["lane_id"]
    memory.auto_checkpoint(
        user_id="u-handoff-8",
        agent_id="claude-code",
        repo_path=repo_path,
        lane_id=lane_id,
        payload={"task_summary": "Lane is active"},
        token=token,
        requester_agent_id="claude-code",
    )

    only_active = memory.get_last_session(
        "u-handoff-8",
        repo=repo_path,
        statuses=["active"],
        token=token,
        requester_agent_id="claude-code",
    )
    assert only_active is not None
    assert only_active["task_summary"] == "Lane is active"
    assert only_active["status"] == "active"

    only_completed = memory.get_last_session(
        "u-handoff-8",
        repo=repo_path,
        statuses=["completed"],
        token=token,
        requester_agent_id="claude-code",
    )
    assert only_completed is not None
    assert only_completed["task_summary"] == "Completed digest only"
    assert only_completed["status"] == "completed"


def test_get_last_session_status_filter_is_case_insensitive(memory, tmp_path):
    repo_path = str(tmp_path)
    token = _token(
        memory,
        user_id="u-handoff-9",
        agent_id="claude-code",
        capabilities=["read_handoff", "write_handoff"],
    )
    memory.save_session_digest(
        "u-handoff-9",
        "claude-code",
        {
            "task_summary": "Paused digest for case-insensitive status test",
            "repo": repo_path,
            "status": "paused",
        },
        token=token,
        requester_agent_id="claude-code",
    )

    resumed = memory.get_last_session(
        "u-handoff-9",
        repo=repo_path,
        statuses=["PAUSED"],
        token=token,
        requester_agent_id="claude-code",
    )
    assert resumed is not None
    assert resumed["status"] == "paused"


def test_get_last_session_rejects_invalid_status_filter(memory, tmp_path):
    repo_path = str(tmp_path)
    token = _token(
        memory,
        user_id="u-handoff-10",
        agent_id="claude-code",
        capabilities=["read_handoff", "write_handoff"],
    )
    memory.save_session_digest(
        "u-handoff-10",
        "claude-code",
        {
            "task_summary": "Digest for invalid status filter test",
            "repo": repo_path,
            "status": "paused",
        },
        token=token,
        requester_agent_id="claude-code",
    )

    with pytest.raises(ValueError, match="Invalid handoff statuses"):
        memory.get_last_session(
            "u-handoff-10",
            repo=repo_path,
            statuses=["running"],
            token=token,
            requester_agent_id="claude-code",
        )
