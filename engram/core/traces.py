"""Benna-Fusi inspired multi-timescale strength traces.

Each memory has three traces (fast, mid, slow) that decay at different rates
and cascade information from fast → mid → slow during sleep cycles.
This mimics how synaptic plasticity operates at multiple timescales in biological memory.
"""

from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Tuple

if TYPE_CHECKING:
    from engram.configs.base import DistillationConfig


def initialize_traces(
    strength: float, is_new: bool = True
) -> Tuple[float, float, float]:
    """Initialize (s_fast, s_mid, s_slow) for a memory.

    New memories: all strength in fast trace.
    Migrated memories: spread across fast and mid.
    """
    strength = max(0.0, min(1.0, float(strength)))
    if is_new:
        return (strength, 0.0, 0.0)
    return (strength, strength * 0.5, 0.0)


def compute_effective_strength(
    s_fast: float, s_mid: float, s_slow: float, config: "DistillationConfig"
) -> float:
    """Weighted combination of three traces into a single effective strength."""
    effective = (
        config.s_fast_weight * s_fast
        + config.s_mid_weight * s_mid
        + config.s_slow_weight * s_slow
    )
    return max(0.0, min(1.0, effective))


def decay_traces(
    s_fast: float,
    s_mid: float,
    s_slow: float,
    last_accessed: datetime,
    access_count: int,
    config: "DistillationConfig",
) -> Tuple[float, float, float]:
    """Decay each trace independently at its own rate.

    Access count provides dampening (more accessed = slower decay),
    mirroring the access-dampened decay in FadeMem.
    """
    if isinstance(last_accessed, str):
        last_accessed = datetime.fromisoformat(last_accessed)
    if last_accessed.tzinfo is None:
        last_accessed = last_accessed.replace(tzinfo=timezone.utc)

    elapsed_days = (datetime.now(timezone.utc) - last_accessed).total_seconds() / 86400.0
    dampening = 1.0 + 0.5 * math.log1p(access_count)

    new_fast = s_fast * math.exp(-config.s_fast_decay_rate * elapsed_days / dampening)
    new_mid = s_mid * math.exp(-config.s_mid_decay_rate * elapsed_days / dampening)
    new_slow = s_slow * math.exp(-config.s_slow_decay_rate * elapsed_days / dampening)

    return (
        max(0.0, min(1.0, new_fast)),
        max(0.0, min(1.0, new_mid)),
        max(0.0, min(1.0, new_slow)),
    )


def cascade_traces(
    s_fast: float,
    s_mid: float,
    s_slow: float,
    config: "DistillationConfig",
    deep_sleep: bool = False,
) -> Tuple[float, float, float]:
    """Transfer strength from faster traces to slower traces.

    Normal: fast → mid transfer only.
    Deep sleep: fast → mid AND mid → slow transfer.
    """
    fast_to_mid = s_fast * config.cascade_fast_to_mid
    new_fast = s_fast - fast_to_mid
    new_mid = s_mid + fast_to_mid

    if deep_sleep:
        mid_to_slow = new_mid * config.cascade_mid_to_slow
        new_mid = new_mid - mid_to_slow
        new_slow = s_slow + mid_to_slow
    else:
        new_slow = s_slow

    return (
        max(0.0, min(1.0, new_fast)),
        max(0.0, min(1.0, new_mid)),
        max(0.0, min(1.0, new_slow)),
    )


def boost_fast_trace(s_fast: float, boost: float) -> float:
    """On access, only the fast trace gets boosted (not mid/slow).

    This models how recent retrieval strengthens short-term plasticity
    without directly affecting consolidated long-term traces.
    """
    return max(0.0, min(1.0, s_fast + boost))
