import json
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from fadem.utils.prompts import FUSION_PROMPT


@dataclass
class FusedMemory:
    content: str
    strength: float
    access_count: int
    source_ids: List[str]
    layer: str = "lml"


def fuse_memories(memories: List[Dict[str, Any]], llm, custom_prompt: Optional[str] = None) -> FusedMemory:
    memories_text = "\n\n".join(
        [
            f"Memory {i + 1} (strength={m.get('strength', 1.0):.2f}, accessed={m.get('access_count', 0)}x, created_at={m.get('created_at', '')}):\n{m.get('memory', '')}"
            for i, m in enumerate(memories)
        ]
    )

    prompt = (custom_prompt or FUSION_PROMPT).format(memories_list=memories_text)

    try:
        response = llm.generate(prompt)
        data = json.loads(response.strip())
        fused_content = data.get("consolidated_memory", "")
    except Exception:
        fused_content = " | ".join([m.get("memory", "") for m in memories])

    avg_strength = sum(m.get("strength", 1.0) for m in memories) / len(memories)
    total_access = sum(m.get("access_count", 0) for m in memories)

    return FusedMemory(
        content=fused_content,
        strength=min(1.0, avg_strength * 1.2),
        access_count=total_access,
        source_ids=[m.get("id", "") for m in memories],
        layer="lml",
    )
