"""Tests for Active Memory Store — signal bus with TTL tiers."""

import os
import tempfile
import time

import pytest

from engram.configs.active import ActiveMemoryConfig
from engram.core.active_memory import ActiveMemoryStore


@pytest.fixture
def store(tmp_path):
    """Create an ActiveMemoryStore with a temporary database."""
    config = ActiveMemoryConfig(
        db_path=str(tmp_path / "active_test.db"),
        ttl_seconds={
            "noise": 1,       # 1 second for fast test
            "notable": 7200,
            "critical": 86400,
            "directive": 0,
        },
    )
    s = ActiveMemoryStore(config)
    yield s
    s.close()


class TestWriteSignal:
    def test_write_event_creates_new(self, store):
        r1 = store.write_signal(key="build", value="failed", signal_type="event")
        r2 = store.write_signal(key="build", value="passed", signal_type="event")
        assert r1["action"] == "created"
        assert r2["action"] == "created"
        assert r1["id"] != r2["id"]

    def test_write_state_upserts(self, store):
        r1 = store.write_signal(key="editing", value="file_a.py", signal_type="state", source_agent_id="agent-1")
        r2 = store.write_signal(key="editing", value="file_b.py", signal_type="state", source_agent_id="agent-1")
        assert r1["action"] == "created"
        assert r2["action"] == "updated"
        assert r1["id"] == r2["id"]

        signals = store.read_signals(user_id="default")
        assert len(signals) == 1
        assert signals[0]["value"] == "file_b.py"

    def test_write_state_different_agents_no_upsert(self, store):
        r1 = store.write_signal(key="editing", value="file_a.py", signal_type="state", source_agent_id="agent-1")
        r2 = store.write_signal(key="editing", value="file_b.py", signal_type="state", source_agent_id="agent-2")
        assert r1["id"] != r2["id"]

        signals = store.read_signals(user_id="default")
        assert len(signals) == 2

    def test_write_directive_upserts_by_key(self, store):
        r1 = store.write_signal(key="use_typescript", value="always", signal_type="directive")
        r2 = store.write_signal(key="use_typescript", value="always use strict mode", signal_type="directive")
        assert r2["action"] == "updated"
        assert r1["id"] == r2["id"]

    def test_directive_forces_directive_tier(self, store):
        store.write_signal(key="rule1", value="test", signal_type="directive", ttl_tier="noise")
        signals = store.read_signals(user_id="default")
        assert signals[0]["ttl_tier"] == "directive"
        assert signals[0]["expires_at"] is None


class TestReadSignals:
    def test_read_empty(self, store):
        signals = store.read_signals(user_id="default")
        assert signals == []

    def test_read_filters_by_scope(self, store):
        store.write_signal(key="a", value="1", scope="global")
        store.write_signal(key="b", value="2", scope="repo", scope_key="/path")
        signals = store.read_signals(scope="repo", scope_key="/path", user_id="default")
        assert len(signals) == 1
        assert signals[0]["key"] == "b"

    def test_read_filters_by_signal_type(self, store):
        store.write_signal(key="a", value="1", signal_type="state")
        store.write_signal(key="b", value="2", signal_type="event")
        signals = store.read_signals(signal_type="event", user_id="default")
        assert len(signals) == 1
        assert signals[0]["key"] == "b"

    def test_read_increments_read_count(self, store):
        store.write_signal(key="x", value="v")
        store.read_signals(user_id="default")
        store.read_signals(user_id="default")
        store.read_signals(user_id="default")
        signals = store.read_signals(user_id="default")
        # read_count reflects value at time of SELECT (before this read's increment)
        assert signals[0]["read_count"] >= 3

    def test_read_tracks_reader_agent(self, store):
        store.write_signal(key="x", value="v")
        store.read_signals(user_id="default", reader_agent_id="agent-A")
        signals = store.read_signals(user_id="default", reader_agent_id="agent-B")
        assert "agent-A" in signals[0]["read_by"]
        assert "agent-B" in signals[0]["read_by"]

    def test_read_priority_order(self, store):
        store.write_signal(key="noise_sig", value="1", ttl_tier="noise")
        store.write_signal(key="critical_sig", value="2", ttl_tier="critical")
        store.write_signal(key="directive_sig", value="3", signal_type="directive")
        signals = store.read_signals(user_id="default")
        tiers = [s["ttl_tier"] for s in signals]
        assert tiers == ["directive", "critical", "noise"]

    def test_read_respects_limit(self, store):
        for i in range(5):
            store.write_signal(key=f"event_{i}", value=str(i), signal_type="event")
        signals = store.read_signals(user_id="default", limit=3)
        assert len(signals) == 3

    def test_read_filters_by_user(self, store):
        store.write_signal(key="a", value="1", user_id="alice")
        store.write_signal(key="b", value="2", user_id="bob")
        signals = store.read_signals(user_id="alice")
        assert len(signals) == 1
        assert signals[0]["key"] == "a"


class TestTTLExpiry:
    def test_noise_expires_quickly(self, store):
        store.write_signal(key="temp", value="gone", ttl_tier="noise")
        # noise TTL is 1 second in test config
        time.sleep(1.5)
        signals = store.read_signals(user_id="default")
        assert len(signals) == 0

    def test_directive_never_expires(self, store):
        store.write_signal(key="rule", value="permanent", signal_type="directive")
        # Even after GC, directive should persist
        store.gc_expired()
        signals = store.read_signals(user_id="default")
        assert len(signals) == 1
        assert signals[0]["signal_type"] == "directive"


class TestClearSignals:
    def test_clear_by_key(self, store):
        store.write_signal(key="a", value="1")
        store.write_signal(key="b", value="2")
        result = store.clear_signals(key="a", user_id="default")
        assert result["deleted"] == 1
        signals = store.read_signals(user_id="default")
        assert len(signals) == 1
        assert signals[0]["key"] == "b"

    def test_clear_by_agent(self, store):
        store.write_signal(key="x", value="1", source_agent_id="agent-1")
        store.write_signal(key="y", value="2", source_agent_id="agent-2")
        result = store.clear_signals(source_agent_id="agent-1", user_id="default")
        assert result["deleted"] == 1

    def test_clear_all_for_user(self, store):
        store.write_signal(key="a", value="1", user_id="u1")
        store.write_signal(key="b", value="2", user_id="u1")
        result = store.clear_signals(user_id="u1")
        assert result["deleted"] == 2


class TestGC:
    def test_gc_removes_expired(self, store):
        store.write_signal(key="temp", value="gone", ttl_tier="noise")
        time.sleep(1.5)
        removed = store.gc_expired()
        assert removed >= 1


class TestConsolidationCandidates:
    def test_directive_is_candidate(self, store):
        store.write_signal(key="rule", value="always use tests", signal_type="directive")
        # With min_age_seconds=0 to bypass age requirement
        candidates = store.get_consolidation_candidates(min_age_seconds=0, min_reads=100)
        assert len(candidates) == 1
        assert candidates[0]["signal_type"] == "directive"

    def test_critical_is_candidate(self, store):
        store.write_signal(key="important", value="critical info", ttl_tier="critical")
        candidates = store.get_consolidation_candidates(min_age_seconds=0, min_reads=100)
        assert len(candidates) == 1

    def test_high_read_is_candidate(self, store):
        store.write_signal(key="popular", value="read a lot")
        for _ in range(5):
            store.read_signals(user_id="default")
        candidates = store.get_consolidation_candidates(min_age_seconds=0, min_reads=3)
        assert len(candidates) >= 1

    def test_mark_consolidated_skips_on_next_run(self, store):
        store.write_signal(key="rule", value="test", signal_type="directive")
        candidates = store.get_consolidation_candidates(min_age_seconds=0)
        assert len(candidates) == 1
        store.mark_consolidated([candidates[0]["id"]])
        candidates2 = store.get_consolidation_candidates(min_age_seconds=0)
        assert len(candidates2) == 0
