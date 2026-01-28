import math
from datetime import datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fadem.configs.base import FadeMemConfig


def calculate_decayed_strength(
    current_strength: float,
    last_accessed: datetime,
    access_count: int,
    layer: str,
    config: "FadeMemConfig",
) -> float:
    if isinstance(last_accessed, str):
        last_accessed = datetime.fromisoformat(last_accessed)

    time_elapsed_days = (datetime.utcnow() - last_accessed).total_seconds() / 86400.0
    decay_rate = config.sml_decay_rate if layer == "sml" else config.lml_decay_rate
    access_dampening = 1 + config.access_dampening_factor * math.log1p(access_count)
    new_strength = current_strength * math.exp(-decay_rate * time_elapsed_days / access_dampening)
    return max(0.0, min(1.0, new_strength))


def should_forget(strength: float, config: "FadeMemConfig") -> bool:
    return strength < config.forgetting_threshold


def should_promote(layer: str, access_count: int, strength: float, config: "FadeMemConfig") -> bool:
    if layer != "sml":
        return False
    return access_count >= config.promotion_access_threshold and strength >= config.promotion_strength_threshold
