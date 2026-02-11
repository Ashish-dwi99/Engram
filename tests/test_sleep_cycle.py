"""Tests for sleep-cycle maintenance flow."""

from __future__ import annotations

from datetime import datetime

import pytest

from engram import Engram


@pytest.fixture
def memory():
    eng = Engram(in_memory=True, provider="mock")
    return eng._memory


def test_sleep_cycle_generates_digest_promotes_and_cleans_refs(memory):
    today = datetime.utcnow().date().isoformat()
    add = memory.add(
        messages="Important retention candidate",
        user_id="u-sleep",
        metadata={"importance": 0.95, "namespace": "default"},
        infer=False,
    )
    memory_id = add["results"][0]["id"]
    # Force stale weak ref so GC has work.
    memory.db.add_memory_subscriber(memory_id, "agent:stale", ref_type="weak", ttl_hours=-1)

    run = memory.run_sleep_cycle(
        user_id="u-sleep",
        date_str=today,
        apply_decay=False,
        cleanup_stale_refs=True,
    )

    assert run["users"]["u-sleep"]["promoted"] >= 1
    assert run["stale_refs_removed"] >= 1

    updated = memory.get(memory_id)
    assert updated is not None
    assert updated.get("layer") == "lml"

    digest = memory.get_daily_digest(user_id="u-sleep", date_str=today)
    assert digest["date"] == today
    assert "top_conflicts" in digest
    assert "top_proposed_consolidations" in digest
