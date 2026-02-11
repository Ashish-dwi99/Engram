"""Tests for reference-aware FadeMem behavior."""

from datetime import datetime, timedelta

import pytest

from engram import Engram


@pytest.fixture
def memory(monkeypatch):
    monkeypatch.setenv("ENGRAM_V2_REF_AWARE_DECAY", "true")
    eng = Engram(in_memory=True, provider="mock")
    return eng._memory


def _create_memory(memory, user_id: str, content: str) -> str:
    added = memory.add(messages=content, user_id=user_id, infer=False)
    return added["results"][0]["id"]


def test_strong_ref_pauses_decay(memory):
    memory_id = _create_memory(memory, "u-decay-strong", "critical memory")
    stale_time = (datetime.utcnow() - timedelta(days=90)).isoformat()
    memory.db.update_memory(memory_id, {"strength": 0.01, "last_accessed": stale_time})

    memory.db.add_memory_subscriber(memory_id, "agent:planner", ref_type="strong")
    result = memory.apply_decay(scope={"user_id": "u-decay-strong"})

    # Memory should not be forgotten due to strong reference.
    assert memory.db.get_memory(memory_id) is not None
    assert result["forgotten"] == 0


def test_weak_ref_dampens_forgetting(memory):
    memory_id = _create_memory(memory, "u-decay-weak", "semi-important memory")
    stale_time = (datetime.utcnow() - timedelta(days=30)).isoformat()
    memory.db.update_memory(memory_id, {"strength": 0.11, "last_accessed": stale_time})

    memory.db.add_memory_subscriber(memory_id, "agent:researcher", ref_type="weak")
    memory.apply_decay(scope={"user_id": "u-decay-weak"})

    mem = memory.db.get_memory(memory_id)
    assert mem is not None
    assert mem["strength"] > 0.0
