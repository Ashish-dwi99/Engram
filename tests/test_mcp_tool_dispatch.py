"""Tests for MCP tool handler registry (Phase 6)."""

import pytest
from engram.mcp_server import _TOOL_HANDLERS


class TestToolHandlerRegistry:
    def test_registry_is_populated(self):
        """The tool handler registry should have entries from decorated handlers."""
        assert len(_TOOL_HANDLERS) > 0

    def test_known_handlers_registered(self):
        """Verify specific handlers are in the registry."""
        expected = {
            "get_memory",
            "update_memory",
            "delete_memory",
            "get_memory_stats",
            "apply_memory_decay",
            "engram_context",
            "get_profile",
            "list_profiles",
            "search_profiles",
        }
        for name in expected:
            assert name in _TOOL_HANDLERS, f"Handler '{name}' not found in registry"

    def test_handlers_are_callable(self):
        """All registered handlers must be callable."""
        for name, handler in _TOOL_HANDLERS.items():
            assert callable(handler), f"Handler '{name}' is not callable"

    def test_handler_signature(self):
        """Handlers should accept (memory, arguments, _session_token, _preview)."""
        import inspect
        for name, handler in _TOOL_HANDLERS.items():
            sig = inspect.signature(handler)
            params = list(sig.parameters.keys())
            assert len(params) == 4, f"Handler '{name}' should have 4 params, got {len(params)}: {params}"
