"""Configuration models for Active Memory (signal bus) and consolidation."""

from enum import Enum
from typing import Dict

from pydantic import BaseModel, Field


class TTLTier(str, Enum):
    NOISE = "noise"          # 30 min
    NOTABLE = "notable"      # 2 hours
    CRITICAL = "critical"    # 24 hours
    DIRECTIVE = "directive"  # permanent (no expiry)


class SignalType(str, Enum):
    STATE = "state"          # Current status ("agent-X is editing file Y")
    EVENT = "event"          # One-shot occurrence ("build failed")
    DIRECTIVE = "directive"  # Permanent user rule ("always use TypeScript")


class SignalScope(str, Enum):
    GLOBAL = "global"        # All agents see it
    REPO = "repo"            # Only agents in same repo
    NAMESPACE = "namespace"  # Only agents in same namespace


class ActiveMemoryConfig(BaseModel):
    """Configuration for the Active Memory signal bus."""
    enabled: bool = True
    db_path: str = Field(default="~/.engram/active.db")
    default_ttl_tier: str = "notable"
    ttl_seconds: Dict[str, int] = Field(default_factory=lambda: {
        "noise": 1800,       # 30 min
        "notable": 7200,     # 2 hours
        "critical": 86400,   # 24 hours
        "directive": 0,      # permanent
    })
    max_signals_per_response: int = 10
    consolidation_enabled: bool = True
    consolidation_min_age_seconds: int = 600
    consolidation_min_reads: int = 3


class ConsolidationConfig(BaseModel):
    """Configuration for active → passive memory consolidation."""
    promote_critical: bool = True
    promote_high_read: bool = True
    promote_read_threshold: int = 3
    directive_to_passive: bool = True
