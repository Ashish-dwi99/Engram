from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, date
from typing import Any, Dict, List, Optional, Union

from fadem.configs.base import MemoryConfig
from fadem.core.decay import calculate_decayed_strength, should_forget, should_promote
from fadem.core.conflict import resolve_conflict
from fadem.core.fusion import fuse_memories
from fadem.core.retrieval import composite_score
from fadem.db.sqlite import SQLiteManager
from fadem.exceptions import FadeMemValidationError
from fadem.memory.base import MemoryBase
from fadem.memory.utils import (
    build_filters_and_metadata,
    matches_filters,
    normalize_categories,
    normalize_messages,
    parse_messages,
    strip_code_fences,
)
from fadem.utils.factory import EmbedderFactory, LLMFactory, VectorStoreFactory
from fadem.utils.prompts import AGENT_MEMORY_EXTRACTION_PROMPT, MEMORY_EXTRACTION_PROMPT

logger = logging.getLogger(__name__)


class Memory(MemoryBase):
    """FadeMem Memory class - drop-in replacement for mem0.Memory."""

    def __init__(self, config: Optional[MemoryConfig] = None):
        self.config = config or MemoryConfig()

        # Ensure vector store config has dims/collection if missing
        self.config.vector_store.config.setdefault("collection_name", self.config.collection_name)
        self.config.vector_store.config.setdefault("embedding_model_dims", self.config.embedding_model_dims)

        self.db = SQLiteManager(self.config.history_db_path)
        self.llm = LLMFactory.create(self.config.llm.provider, self.config.llm.config)
        self.embedder = EmbedderFactory.create(self.config.embedder.provider, self.config.embedder.config)
        self.vector_store = VectorStoreFactory.create(self.config.vector_store.provider, self.config.vector_store.config)
        self.fadem_config = self.config.fadem

    @classmethod
    def from_config(cls, config_dict: Dict[str, Any]):
        return cls(MemoryConfig(**config_dict))

    def add(
        self,
        messages: Union[str, List[Dict[str, str]]],
        user_id: str = None,
        agent_id: str = None,
        run_id: str = None,
        app_id: str = None,
        metadata: Dict[str, Any] = None,
        filters: Dict[str, Any] = None,
        categories: List[str] = None,
        immutable: bool = False,
        expiration_date: str = None,
        infer: bool = True,
        prompt: str = None,
        includes: str = None,
        excludes: str = None,
        initial_layer: str = "auto",
        initial_strength: float = 1.0,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        processed_metadata, effective_filters = build_filters_and_metadata(
            user_id=user_id,
            agent_id=agent_id,
            run_id=run_id,
            input_metadata=metadata,
            input_filters=filters,
        )

        messages_list = normalize_messages(messages)

        if infer:
            memories_to_add = self._extract_memories(
                messages_list,
                processed_metadata,
                prompt=prompt,
                includes=includes,
                excludes=excludes,
            )
        else:
            memories_to_add = []
            for msg in messages_list:
                role = msg.get("role")
                if role == "system":
                    continue
                content = msg.get("content")
                if not content:
                    continue
                mem_meta = dict(processed_metadata)
                mem_meta["role"] = role
                if msg.get("name"):
                    mem_meta["actor_id"] = msg.get("name")
                memories_to_add.append({"content": content, "metadata": mem_meta})

        results: List[Dict[str, Any]] = []
        for mem in memories_to_add:
            content = mem.get("content", "").strip()
            if not content:
                continue

            mem_categories = normalize_categories(categories or mem.get("categories"))
            mem_metadata = dict(processed_metadata)
            mem_metadata.update(mem.get("metadata", {}))
            if app_id:
                mem_metadata["app_id"] = app_id

            embedding = self.embedder.embed(content, memory_action="add")

            # Conflict resolution against nearest memory in scope
            event = "ADD"
            existing = self._find_similar(embedding, effective_filters)
            if existing and self.fadem_config.enable_forgetting:
                resolution = resolve_conflict(existing, content, self.llm, self.config.custom_conflict_prompt)

                if resolution.classification == "CONTRADICTORY":
                    self.delete(existing["id"])
                    event = "UPDATE"
                elif resolution.classification == "SUBSUMES":
                    content = resolution.merged_content or content
                    self.delete(existing["id"])
                    event = "UPDATE"
                elif resolution.classification == "SUBSUMED":
                    # Boost existing memory and skip new
                    boosted_strength = min(1.0, float(existing.get("strength", 1.0)) + 0.05)
                    self.db.update_memory(existing["id"], {"strength": boosted_strength})
                    self.db.increment_access(existing["id"])
                    results.append(
                        {
                            "id": existing["id"],
                            "memory": existing.get("memory", ""),
                            "event": "NOOP",
                            "layer": existing.get("layer", "sml"),
                            "strength": boosted_strength,
                        }
                    )
                    continue

            layer = initial_layer
            if layer == "auto":
                layer = "sml"

            memory_id = str(uuid.uuid4())
            memory_data = {
                "id": memory_id,
                "memory": content,
                "user_id": user_id,
                "agent_id": agent_id,
                "run_id": run_id,
                "app_id": app_id,
                "metadata": mem_metadata,
                "categories": mem_categories,
                "immutable": immutable,
                "expiration_date": expiration_date,
                "layer": layer,
                "strength": initial_strength,
                "embedding": embedding,
            }

            self.db.add_memory(memory_data)
            payload = dict(mem_metadata)
            payload.update({
                "memory": content,
                "user_id": user_id,
                "agent_id": agent_id,
                "run_id": run_id,
                "app_id": app_id,
                "categories": mem_categories,
            })
            self.vector_store.insert([embedding], payloads=[payload], ids=[memory_id])

            results.append(
                {
                    "id": memory_id,
                    "memory": content,
                    "event": event,
                    "layer": layer,
                    "strength": initial_strength,
                }
            )

        return {"results": results}

    def search(
        self,
        query: str,
        user_id: str = None,
        agent_id: str = None,
        run_id: str = None,
        app_id: str = None,
        filters: Dict[str, Any] = None,
        categories: List[str] = None,
        limit: int = 100,
        rerank: bool = True,
        keyword_search: bool = False,
        min_strength: float = 0.1,
        boost_on_access: bool = True,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        _, effective_filters = build_filters_and_metadata(
            user_id=user_id,
            agent_id=agent_id,
            run_id=run_id,
            input_filters=filters,
        )
        if app_id:
            effective_filters["app_id"] = app_id

        query_embedding = self.embedder.embed(query, memory_action="search")
        vector_results = self.vector_store.search(query=query, vectors=query_embedding, limit=limit * 2, filters=effective_filters)

        results: List[Dict[str, Any]] = []
        for vr in vector_results:
            memory = self.db.get_memory(vr.id)
            if not memory:
                continue

            # Skip expired memories
            if self._is_expired(memory):
                self.delete(memory["id"])
                continue

            if memory.get("strength", 1.0) < min_strength:
                continue
            if categories and not any(c in memory.get("categories", []) for c in categories):
                continue
            if filters and not matches_filters({**memory, **memory.get("metadata", {})}, filters):
                continue

            similarity = float(vr.score)
            strength = float(memory.get("strength", 1.0))
            combined = composite_score(similarity, strength)

            if boost_on_access:
                self.db.increment_access(memory["id"])
                self._check_promotion(memory["id"])

            results.append(
                {
                    "id": memory["id"],
                    "memory": memory.get("memory", ""),
                    "user_id": memory.get("user_id"),
                    "agent_id": memory.get("agent_id"),
                    "run_id": memory.get("run_id"),
                    "app_id": memory.get("app_id"),
                    "metadata": memory.get("metadata", {}),
                    "categories": memory.get("categories", []),
                    "immutable": memory.get("immutable", False),
                    "created_at": memory.get("created_at"),
                    "updated_at": memory.get("updated_at"),
                    "score": similarity,
                    "strength": strength,
                    "layer": memory.get("layer", "sml"),
                    "access_count": memory.get("access_count", 0),
                    "last_accessed": memory.get("last_accessed"),
                    "composite_score": combined,
                }
            )

        results.sort(key=lambda x: x["composite_score"], reverse=True)
        return {"results": results[:limit]}

    def get(self, memory_id: str) -> Optional[Dict[str, Any]]:
        memory = self.db.get_memory(memory_id)
        if memory:
            self.db.increment_access(memory_id)
        return memory

    def get_all(
        self,
        user_id: str = None,
        agent_id: str = None,
        run_id: str = None,
        app_id: str = None,
        filters: Dict[str, Any] = None,
        categories: List[str] = None,
        limit: int = 100,
        layer: str = None,
        min_strength: float = 0.0,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        _, effective_filters = build_filters_and_metadata(
            user_id=user_id,
            agent_id=agent_id,
            run_id=run_id,
            input_filters=filters,
        )
        if app_id:
            effective_filters["app_id"] = app_id

        memories = self.db.get_all_memories(
            user_id=user_id,
            agent_id=agent_id,
            run_id=run_id,
            app_id=app_id,
            layer=layer,
            min_strength=min_strength,
        )

        if categories:
            memories = [m for m in memories if any(c in m.get("categories", []) for c in categories)]

        if filters:
            memories = [m for m in memories if matches_filters({**m, **m.get("metadata", {})}, filters)]

        memories = [m for m in memories if not self._is_expired(m)]
        return {"results": memories[:limit]}

    def update(self, memory_id: str, data: str) -> Dict[str, Any]:
        new_embedding = self.embedder.embed(data, memory_action="update")
        success = self.db.update_memory(memory_id, {"memory": data, "embedding": new_embedding})
        existing = self.vector_store.get(memory_id)
        if existing:
            payload = existing.payload
            payload["memory"] = data
            self.vector_store.update(memory_id, vector=new_embedding, payload=payload)
        return {"id": memory_id, "memory": data, "event": "UPDATE" if success else "ERROR"}

    def delete(self, memory_id: str) -> Dict[str, Any]:
        self.db.delete_memory(memory_id, use_tombstone=self.fadem_config.use_tombstone_deletion)
        self.vector_store.delete(memory_id)
        return {"id": memory_id, "deleted": True}

    def delete_all(
        self,
        user_id: str = None,
        agent_id: str = None,
        run_id: str = None,
        app_id: str = None,
        filters: Dict[str, Any] = None,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        if not any([user_id, agent_id, run_id, app_id, filters]):
            raise FadeMemValidationError(
                "At least one filter is required to delete all memories. Use reset() to clear everything.",
                error_code="VALIDATION_004",
            )
        memories = self.db.get_all_memories(user_id=user_id, agent_id=agent_id, run_id=run_id, app_id=app_id)
        if filters:
            memories = [m for m in memories if matches_filters({**m, **m.get("metadata", {})}, filters)]

        count = 0
        for memory in memories:
            self.delete(memory["id"])
            count += 1
        return {"deleted_count": count}

    def history(self, memory_id: str) -> List[Dict[str, Any]]:
        return self.db.get_history(memory_id)

    def reset(self) -> None:
        memories = self.db.get_all_memories(include_tombstoned=True)
        for mem in memories:
            self.delete(mem["id"])
        if hasattr(self.vector_store, "reset"):
            self.vector_store.reset()

    # FadeMem-specific methods
    def apply_decay(self, scope: Dict[str, Any] = None) -> Dict[str, Any]:
        if not self.fadem_config.enable_forgetting:
            return {"decayed": 0, "forgotten": 0, "promoted": 0}

        memories = self.db.get_all_memories(
            user_id=scope.get("user_id") if scope else None,
            agent_id=scope.get("agent_id") if scope else None,
            run_id=scope.get("run_id") if scope else None,
            app_id=scope.get("app_id") if scope else None,
        )

        decayed = 0
        forgotten = 0
        promoted = 0

        for memory in memories:
            if memory.get("immutable"):
                continue

            new_strength = calculate_decayed_strength(
                current_strength=memory.get("strength", 1.0),
                last_accessed=memory.get("last_accessed", datetime.utcnow().isoformat()),
                access_count=memory.get("access_count", 0),
                layer=memory.get("layer", "sml"),
                config=self.fadem_config,
            )

            if should_forget(new_strength, self.fadem_config):
                self.delete(memory["id"])
                forgotten += 1
                continue

            if new_strength != memory.get("strength"):
                self.db.update_memory(memory["id"], {"strength": new_strength})
                self.db.log_event(memory["id"], "DECAY", old_strength=memory.get("strength"), new_strength=new_strength)
                decayed += 1

            if should_promote(
                memory.get("layer", "sml"),
                memory.get("access_count", 0),
                new_strength,
                self.fadem_config,
            ):
                self.db.update_memory(memory["id"], {"layer": "lml"})
                self.db.log_event(memory["id"], "PROMOTE", old_layer="sml", new_layer="lml")
                promoted += 1

        if self.fadem_config.use_tombstone_deletion:
            self.db.purge_tombstoned()

        self.db.log_decay(decayed, forgotten, promoted)
        return {"decayed": decayed, "forgotten": forgotten, "promoted": promoted}

    def fuse_memories(self, memory_ids: List[str], user_id: str = None) -> Dict[str, Any]:
        memories = [self.db.get_memory(mid) for mid in memory_ids]
        memories = [m for m in memories if m]
        if len(memories) < 2:
            return {"error": "Need at least 2 memories to fuse"}

        fused = fuse_memories(memories, self.llm, self.config.custom_fusion_prompt)
        result = self.add(
            fused.content,
            user_id=user_id or memories[0].get("user_id"),
            agent_id=memories[0].get("agent_id"),
            run_id=memories[0].get("run_id"),
            app_id=memories[0].get("app_id"),
            initial_layer=fused.layer,
            initial_strength=fused.strength,
            infer=False,
        )

        for mid in memory_ids:
            self.delete(mid)

        fused_id = result.get("results", [{}])[0].get("id") if result.get("results") else None
        return {"fused_id": fused_id, "source_ids": memory_ids, "fused_memory": fused.content}

    def get_stats(self, user_id: str = None) -> Dict[str, Any]:
        memories = self.db.get_all_memories(user_id=user_id)
        sml_count = sum(1 for m in memories if m.get("layer") == "sml")
        lml_count = sum(1 for m in memories if m.get("layer") == "lml")
        strengths = [m.get("strength", 1.0) for m in memories]
        avg_strength = sum(strengths) / len(strengths) if strengths else 0.0

        return {
            "total": len(memories),
            "sml_count": sml_count,
            "lml_count": lml_count,
            "avg_strength": round(avg_strength, 3),
        }

    def promote(self, memory_id: str) -> Dict[str, Any]:
        return {"success": self.db.update_memory(memory_id, {"layer": "lml"})}

    def demote(self, memory_id: str) -> Dict[str, Any]:
        return {"success": self.db.update_memory(memory_id, {"layer": "sml"})}

    # Internal helpers
    def _extract_memories(
        self,
        messages: List[Dict[str, Any]],
        metadata: Dict[str, Any],
        prompt: Optional[str] = None,
        includes: Optional[str] = None,
        excludes: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        conversation = parse_messages(messages)
        existing = self.db.get_all_memories(
            user_id=metadata.get("user_id"),
            agent_id=metadata.get("agent_id"),
            run_id=metadata.get("run_id"),
            app_id=metadata.get("app_id"),
        )
        existing_text = "\n".join([m.get("memory", "") for m in existing])

        if prompt or self.config.custom_fact_extraction_prompt:
            extraction_prompt = prompt or self.config.custom_fact_extraction_prompt
        else:
            if self._should_use_agent_memory_extraction(messages, metadata):
                extraction_prompt = AGENT_MEMORY_EXTRACTION_PROMPT
            else:
                extraction_prompt = MEMORY_EXTRACTION_PROMPT
        prompt_text = extraction_prompt.format(conversation=conversation, existing_memories=existing_text)

        try:
            response = self.llm.generate(prompt_text)
            data = strip_code_fences(response)
            if not data:
                return []
            parsed = json.loads(data)
            memories = parsed.get("memories", [])
            extracted = [
                {
                    "content": m.get("content", ""),
                    "categories": [m.get("category")] if m.get("category") else [],
                    "metadata": {"importance": m.get("importance"), "confidence": m.get("confidence")},
                }
                for m in memories
                if isinstance(m, dict)
            ]
            if includes:
                extracted = [m for m in extracted if includes.lower() in m.get("content", "").lower()]
            if excludes:
                extracted = [m for m in extracted if excludes.lower() not in m.get("content", "").lower()]
            return extracted
        except Exception as exc:
            logger.warning(f"Failed to parse extraction response: {exc}")
            # Fallback: add last user message
            last_user = next((m for m in reversed(messages) if m.get("role") == "user"), None)
            if last_user:
                return [{"content": last_user.get("content", "") }]
            return []

    def _should_use_agent_memory_extraction(self, messages: List[Dict[str, Any]], metadata: Dict[str, Any]) -> bool:
        has_agent_id = metadata.get("agent_id") is not None
        has_assistant_messages = any(msg.get("role") == "assistant" for msg in messages)
        return has_agent_id and has_assistant_messages

    def _find_similar(self, embedding: List[float], filters: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        results = self.vector_store.search(query=None, vectors=embedding, limit=1, filters=filters)
        if results and results[0].score >= self.fadem_config.conflict_similarity_threshold:
            return self.db.get_memory(results[0].id)
        return None

    def _check_promotion(self, memory_id: str) -> None:
        memory = self.db.get_memory(memory_id)
        if memory and should_promote(
            memory.get("layer", "sml"),
            memory.get("access_count", 0),
            memory.get("strength", 1.0),
            self.fadem_config,
        ):
            self.db.update_memory(memory_id, {"layer": "lml"})
            self.db.log_event(memory_id, "PROMOTE", old_layer="sml", new_layer="lml")

    def _is_expired(self, memory: Dict[str, Any]) -> bool:
        expiration = memory.get("expiration_date")
        if not expiration:
            return False
        try:
            exp_date = date.fromisoformat(expiration)
        except Exception:
            return False
        return date.today() > exp_date
