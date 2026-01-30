"""engram package exports.

engram: Biologically-inspired memory for AI agents
- engram: Dual-layer (SML/LML) with natural decay
- EchoMem: Multi-modal encoding for stronger retention
- CategoryMem: Dynamic hierarchical category organization
"""

from engram.memory.main import Memory
from engram.memory.client import MemoryClient
from engram.memory.async_memory import AsyncMemory
from engram.core.category import CategoryProcessor, Category, CategoryType, CategoryMatch
from engram.core.echo import EchoProcessor, EchoDepth, EchoResult
from engram.configs.base import MemoryConfig, FadeMemConfig, EchoMemConfig, CategoryMemConfig

__version__ = "0.1.3"  # CategoryMem release
__all__ = [
    # Main classes
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
]
