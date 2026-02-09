"""Re-ranking helpers for dual retrieval."""

from __future__ import annotations

from typing import Dict, List, Set


def intersection_promote(
    semantic_results: List[Dict],
    episodic_scene_results: List[Dict],
) -> List[Dict]:
    """Promote semantic results that also appear in episodic scenes.

    Relative order among promoted items follows original semantic ranking.
    """
    episodic_memory_ids: Set[str] = set()
    for scene in episodic_scene_results:
        for mid in scene.get("memory_ids", []) or []:
            episodic_memory_ids.add(str(mid))

    if not episodic_memory_ids:
        return semantic_results

    promoted: List[Dict] = []
    others: List[Dict] = []
    for item in semantic_results:
        mid = str(item.get("id"))
        if mid in episodic_memory_ids:
            enriched = dict(item)
            enriched["episodic_match"] = True
            promoted.append(enriched)
        else:
            enriched = dict(item)
            enriched["episodic_match"] = False
            others.append(enriched)

    return promoted + others
