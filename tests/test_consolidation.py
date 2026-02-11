"""Tests for Active → Passive memory consolidation engine."""

from unittest.mock import MagicMock, patch

import pytest

from engram.configs.active import ActiveMemoryConfig
from engram.core.active_memory import ActiveMemoryStore
from engram.core.consolidation import ConsolidationEngine


@pytest.fixture
def active_store(tmp_path):
    config = ActiveMemoryConfig(
        db_path=str(tmp_path / "consolidation_test.db"),
        consolidation_min_age_seconds=0,  # no age requirement for tests
        consolidation_min_reads=2,
    )
    s = ActiveMemoryStore(config)
    yield s
    s.close()


@pytest.fixture
def mock_memory():
    memory = MagicMock()
    memory.add.return_value = {"results": [{"id": "mem-1"}]}
    return memory


@pytest.fixture
def engine(active_store, mock_memory):
    config = ActiveMemoryConfig(
        consolidation_min_age_seconds=0,
        consolidation_min_reads=2,
    )
    return ConsolidationEngine(active_store, mock_memory, config)


class TestConsolidation:
    def test_directive_promoted(self, active_store, engine, mock_memory):
        active_store.write_signal(key="rule", value="always use tests", signal_type="directive")
        result = engine.run_cycle()
        assert result["promoted"] == 1
        mock_memory.add.assert_called_once()
        call_kwargs = mock_memory.add.call_args
        assert call_kwargs.kwargs["immutable"] is True
        assert call_kwargs.kwargs["initial_layer"] == "lml"

    def test_critical_promoted(self, active_store, engine, mock_memory):
        active_store.write_signal(key="important", value="critical info", ttl_tier="critical")
        result = engine.run_cycle()
        assert result["promoted"] == 1
        call_kwargs = mock_memory.add.call_args
        assert call_kwargs.kwargs["immutable"] is False
        assert call_kwargs.kwargs["initial_layer"] == "sml"

    def test_high_read_promoted(self, active_store, engine, mock_memory):
        active_store.write_signal(key="popular", value="frequently read", ttl_tier="notable")
        # Read 3 times to exceed threshold of 2
        for _ in range(3):
            active_store.read_signals(user_id="default")
        result = engine.run_cycle()
        assert result["promoted"] >= 1

    def test_low_read_not_promoted(self, active_store, engine, mock_memory):
        active_store.write_signal(key="unpopular", value="barely read", ttl_tier="notable")
        # Only 1 read, below threshold of 2
        active_store.read_signals(user_id="default")
        result = engine.run_cycle()
        assert result["promoted"] == 0
        mock_memory.add.assert_not_called()

    def test_already_consolidated_skipped(self, active_store, engine, mock_memory):
        active_store.write_signal(key="rule", value="test", signal_type="directive")
        # First cycle promotes
        result1 = engine.run_cycle()
        assert result1["promoted"] == 1
        mock_memory.add.reset_mock()
        # Second cycle should skip (already consolidated)
        result2 = engine.run_cycle()
        assert result2["promoted"] == 0
        mock_memory.add.assert_not_called()

    def test_content_format(self, active_store, engine, mock_memory):
        active_store.write_signal(key="coding_style", value="use type hints", signal_type="directive")
        engine.run_cycle()
        call_kwargs = mock_memory.add.call_args
        assert "[coding_style]" in call_kwargs.kwargs["messages"]
        assert "use type hints" in call_kwargs.kwargs["messages"]

    def test_metadata_source(self, active_store, engine, mock_memory):
        active_store.write_signal(key="test_key", value="test_val", signal_type="directive")
        engine.run_cycle()
        call_kwargs = mock_memory.add.call_args
        metadata = call_kwargs.kwargs["metadata"]
        assert metadata["source"] == "active_signal"
        assert metadata["signal_key"] == "test_key"
        assert metadata["signal_type"] == "directive"

    def test_run_cycle_stats(self, active_store, engine, mock_memory):
        active_store.write_signal(key="rule1", value="a", signal_type="directive")
        active_store.write_signal(key="rule2", value="b", signal_type="directive")
        active_store.write_signal(key="noise", value="c", ttl_tier="noise")
        result = engine.run_cycle()
        assert result["promoted"] == 2
        assert result["checked"] == 2  # noise is not a candidate
        assert result["errors"] == 0
