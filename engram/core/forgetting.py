"""Advanced forgetting mechanisms for CLS Distillation Memory.

Three biologically-inspired forgetting mechanisms beyond simple exponential decay:
1. InterferencePruner — contradictory memories demote each other
2. RedundancyCollapser — near-duplicate memories auto-fuse
3. HomeostaticNormalizer — memory budget enforcement with pressure-based decay
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Dict, List, Optional

if TYPE_CHECKING:
    from engram.configs.base import DistillationConfig, FadeMemConfig
    from engram.db.sqlite import SQLiteManager

logger = logging.getLogger(__name__)


class InterferencePruner:
    """Demote contradictory memories discovered during decay cycles.

    For memories above a minimum strength, finds nearest neighbors and
    checks for contradiction. If contradictory, the weaker memory gets demoted.
    """

    def __init__(
        self,
        db: "SQLiteManager",
        config: "DistillationConfig",
        fadem_config: "FadeMemConfig",
        resolve_conflict_fn=None,
        search_fn=None,
        llm=None,
    ):
        self.db = db
        self.config = config
        self.fadem_config = fadem_config
        self.resolve_conflict_fn = resolve_conflict_fn
        self.search_fn = search_fn
        self.llm = llm

    def run(
        self,
        memories: List[Dict[str, Any]],
        user_id: Optional[str] = None,
    ) -> Dict[str, int]:
        """Check memories for interference and demote contradictions.

        Returns {"checked": N, "demoted": N}.
        """
        if not self.config.enable_interference_pruning:
            return {"checked": 0, "demoted": 0}

        if not self.resolve_conflict_fn or not self.search_fn:
            return {"checked": 0, "demoted": 0}

        checked = 0
        demoted = 0
        min_strength = 0.2

        for memory in memories:
            if memory.get("immutable"):
                continue
            strength = float(memory.get("strength", 0.0))
            if strength < min_strength:
                continue

            embedding = memory.get("embedding")
            if not embedding:
                continue

            checked += 1

            # Find nearest neighbor
            try:
                filters = {"user_id": user_id} if user_id else {}
                neighbors = self.search_fn(
                    query="",
                    vectors=embedding,
                    limit=2,
                    filters=filters,
                )
                # Skip self
                neighbors = [n for n in neighbors if n.id != memory["id"]]
                if not neighbors:
                    continue

                nearest = neighbors[0]
                similarity = float(nearest.score)

                if similarity < self.fadem_config.conflict_similarity_threshold:
                    continue

                # Fetch the neighbor memory from DB
                neighbor_mem = self.db.get_memory(nearest.id)
                if not neighbor_mem:
                    continue

                # Check for contradiction
                resolution = self.resolve_conflict_fn(
                    neighbor_mem, memory.get("memory", ""), self.llm
                )

                if resolution and resolution.classification == "CONTRADICTORY":
                    # Demote the weaker one
                    mem_strength = float(memory.get("strength", 0.0))
                    neighbor_strength = float(neighbor_mem.get("strength", 0.0))

                    if mem_strength <= neighbor_strength:
                        target_id = memory["id"]
                        old_strength = mem_strength
                    else:
                        target_id = neighbor_mem["id"]
                        old_strength = neighbor_strength

                    new_strength = old_strength * 0.3
                    self.db.update_memory(target_id, {"strength": new_strength})
                    self.db.log_event(
                        target_id,
                        "INTERFERENCE_DEMOTE",
                        old_strength=old_strength,
                        new_strength=new_strength,
                    )
                    demoted += 1

            except Exception as e:
                logger.debug("Interference check failed for %s: %s", memory.get("id"), e)

        return {"checked": checked, "demoted": demoted}


class RedundancyCollapser:
    """Auto-fuse near-duplicate memories to reduce bloat.

    During decay cycles, finds clusters of highly similar memories
    and fuses them using the existing fusion pipeline.
    """

    def __init__(
        self,
        db: "SQLiteManager",
        config: "DistillationConfig",
        fuse_fn=None,
        search_fn=None,
    ):
        self.db = db
        self.config = config
        self.fuse_fn = fuse_fn
        self.search_fn = search_fn

    def run(
        self,
        memories: List[Dict[str, Any]],
        user_id: Optional[str] = None,
    ) -> Dict[str, int]:
        """Find and fuse redundant memory groups.

        Returns {"groups_fused": N, "memories_fused": N}.
        """
        if not self.config.enable_redundancy_collapse:
            return {"groups_fused": 0, "memories_fused": 0}

        if not self.fuse_fn or not self.search_fn:
            return {"groups_fused": 0, "memories_fused": 0}

        threshold = self.config.redundancy_collapse_threshold
        groups_fused = 0
        memories_fused = 0
        already_fused = set()

        for memory in memories:
            mid = memory.get("id")
            if mid in already_fused:
                continue
            if memory.get("immutable"):
                continue

            embedding = memory.get("embedding")
            if not embedding:
                continue

            try:
                filters = {"user_id": user_id} if user_id else {}
                neighbors = self.search_fn(
                    query="",
                    vectors=embedding,
                    limit=5,
                    filters=filters,
                )
                # Find highly similar memories
                group_ids = [mid]
                for n in neighbors:
                    if n.id == mid or n.id in already_fused:
                        continue
                    n_mem = self.db.get_memory(n.id)
                    if not n_mem or n_mem.get("immutable"):
                        continue
                    if float(n.score) >= threshold:
                        group_ids.append(n.id)

                if len(group_ids) >= 2:
                    result = self.fuse_fn(group_ids, user_id=user_id)
                    if result and not result.get("error"):
                        already_fused.update(group_ids)
                        groups_fused += 1
                        memories_fused += len(group_ids)

            except Exception as e:
                logger.debug("Redundancy collapse failed for %s: %s", mid, e)

        return {"groups_fused": groups_fused, "memories_fused": memories_fused}


class HomeostaticNormalizer:
    """Enforce memory budgets per namespace with pressure-based decay.

    When a namespace exceeds its budget, applies extra decay pressure
    to the weakest memories proportional to the excess ratio.
    """

    def __init__(
        self,
        db: "SQLiteManager",
        config: "DistillationConfig",
        fadem_config: "FadeMemConfig",
        delete_fn=None,
    ):
        self.db = db
        self.config = config
        self.fadem_config = fadem_config
        self.delete_fn = delete_fn

    def run(
        self,
        user_id: str,
    ) -> Dict[str, Any]:
        """Apply homeostatic pressure to namespaces over budget.

        Returns {"namespaces_over_budget": N, "pressured": N, "forgotten": N}.
        """
        if not self.config.enable_homeostasis:
            return {"namespaces_over_budget": 0, "pressured": 0, "forgotten": 0}

        counts = self.db.get_memory_count_by_namespace(user_id)
        budget = self.config.homeostasis_budget_per_namespace
        pressure_factor = self.config.homeostasis_pressure_factor

        namespaces_over = 0
        total_pressured = 0
        total_forgotten = 0

        for namespace, count in counts.items():
            if count <= budget:
                continue

            namespaces_over += 1
            excess_ratio = (count - budget) / budget

            # Fetch weakest memories in this namespace
            weak_memories = self.db.get_all_memories(
                user_id=user_id,
                namespace=namespace,
                min_strength=0.0,
                limit=count,
            )

            # Sort by strength ascending (weakest first)
            weak_memories.sort(key=lambda m: float(m.get("strength", 0.0)))

            for memory in weak_memories:
                if memory.get("immutable"):
                    continue

                strength = float(memory.get("strength", 0.0))
                # Apply extra decay proportional to excess
                pressure = strength * pressure_factor * excess_ratio
                new_strength = max(0.0, strength - pressure)

                if new_strength < self.fadem_config.forgetting_threshold:
                    if self.delete_fn:
                        try:
                            self.delete_fn(memory["id"])
                            total_forgotten += 1
                        except Exception as e:
                            logger.debug("Homeostasis delete failed for %s: %s", memory["id"], e)
                else:
                    self.db.update_memory(memory["id"], {"strength": new_strength})
                    total_pressured += 1

        return {
            "namespaces_over_budget": namespaces_over,
            "pressured": total_pressured,
            "forgotten": total_forgotten,
        }
