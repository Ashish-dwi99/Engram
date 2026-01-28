import json
from dataclasses import dataclass
from typing import Any, Dict, Optional

from fadem.utils.prompts import CONFLICT_RESOLUTION_PROMPT


@dataclass
class ConflictResolution:
    classification: str
    confidence: float
    merged_content: Optional[str] = None
    explanation: str = ""


def resolve_conflict(existing_memory: Dict[str, Any], new_content: str, llm, custom_prompt: Optional[str] = None) -> ConflictResolution:
    prompt = (custom_prompt or CONFLICT_RESOLUTION_PROMPT).format(
        existing_memory=existing_memory.get("memory", ""),
        existing_created_at=existing_memory.get("created_at", "unknown"),
        existing_last_accessed=existing_memory.get("last_accessed", "unknown"),
        existing_access_count=existing_memory.get("access_count", 0),
        existing_strength=existing_memory.get("strength", 1.0),
        new_memory=new_content,
    )

    try:
        response = llm.generate(prompt)
        data = json.loads(response.strip())
        return ConflictResolution(
            classification=data.get("classification", "COMPATIBLE"),
            confidence=float(data.get("confidence", 0.5)),
            merged_content=data.get("merged_content"),
            explanation=data.get("explanation", ""),
        )
    except Exception:
        return ConflictResolution(
            classification="COMPATIBLE",
            confidence=0.5,
            merged_content=None,
            explanation="Failed to parse LLM response",
        )
