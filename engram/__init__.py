"""engram package exports.

engram: Biologically-inspired memory for AI agents
- FadeMem: Dual-layer (SML/LML) with natural decay
- EchoMem: Multi-modal encoding for stronger retention
- CategoryMem: Dynamic hierarchical category organization

Quick Start:
    from engram import Engram

    memory = Engram()
    memory.add("User prefers Python", user_id="u123")
    results = memory.search("programming preferences", user_id="u123")
"""

from engram.simple import Engram
from engram.memory.main import Memory
from engram.memory.client import MemoryClient
from engram.memory.async_memory import AsyncMemory
from engram.core.category import CategoryProcessor, Category, CategoryType, CategoryMatch
from engram.core.echo import EchoProcessor, EchoDepth, EchoResult
from engram.configs.base import MemoryConfig, FadeMemConfig, EchoMemConfig, CategoryMemConfig, ScopeConfig

__version__ = "0.2.0"  # REST API + Simplified SDK
__all__ = [
    # Simplified interface (recommended)
    "Engram",
    # Full interface
    "Memory",
    "MemoryClient",
    "AsyncMemory",
    # CategoryMem
    "CategoryProcessor",
    "Category",
    "CategoryType",
    "CategoryMatch",
    # EchoMem
    "EchoProcessor",
    "EchoDepth",
    "EchoResult",
    # Config
    "MemoryConfig",
    "FadeMemConfig",
    "EchoMemConfig",
    "CategoryMemConfig",
    "ScopeConfig",
]
