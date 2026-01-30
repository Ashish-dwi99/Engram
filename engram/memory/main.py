from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, date
from typing import Any, Dict, List, Optional, Union

from engram.configs.base import MemoryConfig
from engram.core.decay import calculate_decayed_strength, should_forget, should_promote
from engram.core.conflict import resolve_conflict
from engram.core.echo import EchoProcessor, EchoDepth
from engram.core.fusion import fuse_memories
from engram.core.retrieval import composite_score
from engram.core.category import CategoryProcessor, CategoryMatch
from engram.db.sqlite import SQLiteManager
from engram.exceptions import FadeMemValidationError
from engram.memory.base import MemoryBase
from engram.memory.utils import (
    build_filters_and_metadata,
    matches_filters,
    normalize_categories,
    normalize_messages,
    parse_messages,
    strip_code_fences,
)
from engram.utils.factory import EmbedderFactory, LLMFactory, VectorStoreFactory
from engram.utils.prompts import AGENT_MEMORY_EXTRACTION_PROMPT, MEMORY_EXTRACTION_PROMPT

logger = logging.getLogger(__name__)


class Memory(MemoryBase):
    """engram Memory class - biologically-inspired memory for AI agents."""

    def __init__(self, config: Optional[MemoryConfig] = None):
        self.config = config or MemoryConfig()

        # Ensure vector store config has dims/collection if missing
        self.config.vector_store.config.setdefault("collection_name", self.config.collection_name)
        self.config.vector_store.config.setdefault("embedding_model_dims", self.config.embedding_model_dims)

        self.db = SQLiteManager(self.config.history_db_path)
        self.llm = LLMFactory.create(self.config.llm.provider, self.config.llm.config)
        self.embedder = EmbedderFactory.create(self.config.embedder.provider, self.config.embedder.config)
        self.vector_store = VectorStoreFactory.create(self.config.vector_store.provider, self.config.vector_store.config)
        self.fadem_config = self.config.engram
        self.echo_config = self.config.echo

        # Initialize EchoMem processor
        if self.echo_config.enable_echo:
            self.echo_processor = EchoProcessor(
                self.llm,
                config={
                    "auto_depth": self.echo_config.auto_depth,
                    "default_depth": self.echo_config.default_depth,
                }
            )
        else:
            self.echo_processor = None

        # Initialize CategoryMem processor
        self.category_config = self.config.category
        if self.category_config.enable_categories:
            self.category_processor = CategoryProcessor(
                llm=self.llm,
                embedder=self.embedder,
                config={
                    "use_llm": self.category_config.use_llm_categorization,
                    "auto_subcategories": self.category_config.auto_create_subcategories,
                    "max_depth": self.category_config.max_category_depth,
                },
            )
            # Load existing categories from DB
            existing_categories = self.db.get_all_categories()
            if existing_categories:
                self.category_processor.load_categories(existing_categories)
        else:
            self.category_processor = None

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
        echo_depth: str = None,  # EchoMem: override echo depth (shallow/medium/deep)
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

            # CategoryMem: Auto-categorize if not provided
            category_match = None
            if (
                self.category_processor
                and self.category_config.auto_categorize
                and not mem_categories
            ):
                category_match = self.category_processor.detect_category(
                    content,
                    metadata=mem_metadata,
                    use_llm=self.category_config.use_llm_categorization,
                )
                mem_categories = [category_match.category_id]
                mem_metadata["category_confidence"] = category_match.confidence
                mem_metadata["category_auto"] = True

            # EchoMem: Process through multi-modal echo encoding
            echo_result = None
            effective_strength = initial_strength
            if self.echo_processor and self.echo_config.enable_echo:
                depth_override = EchoDepth(echo_depth) if echo_depth else None
                echo_result = self.echo_processor.process(content, depth=depth_override)
                # Apply strength multiplier from echo depth
                effective_strength = initial_strength * echo_result.strength_multiplier
                # Add echo metadata
                mem_metadata.update(echo_result.to_metadata())
                # Auto-categorize if not provided
                if not mem_categories and echo_result.category:
                    mem_categories = [echo_result.category]

            # Choose embedding: question_form (query-optimized) or raw content
            if (
                echo_result
                and echo_result.question_form
                and self.echo_config.use_question_embedding
            ):
                embedding = self.embedder.embed(echo_result.question_form, memory_action="add")
            else:
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
                "strength": effective_strength,
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

            # CategoryMem: Update category stats
            if self.category_processor and mem_categories:
                for cat_id in mem_categories:
                    self.category_processor.update_category_stats(
                        cat_id, effective_strength, is_addition=True
                    )

            results.append(
                {
                    "id": memory_id,
                    "memory": content,
                    "event": event,
                    "layer": layer,
                    "strength": effective_strength,
                    "echo_depth": echo_result.echo_depth.value if echo_result else None,
                    "categories": mem_categories,
                }
            )

        # Persist categories after batch
        if self.category_processor:
            self._persist_categories()

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
        use_echo_rerank: bool = True,  # EchoMem: use echo metadata for re-ranking
        use_category_boost: bool = True,  # CategoryMem: boost by category relevance
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

        # Prepare query terms for echo-based re-ranking
        query_lower = query.lower()
        query_terms = set(query_lower.split())

        # CategoryMem: Detect relevant categories for the query
        query_category_id = None
        related_category_ids = set()
        if self.category_processor and use_category_boost:
            category_match = self.category_processor.detect_category(
                query, use_llm=False  # Fast match only for search
            )
            if category_match.confidence > 0.4:
                query_category_id = category_match.category_id
                related_category_ids = set(
                    self.category_processor.find_related_categories(query_category_id)
                )
                # Record access to category
                self.category_processor.access_category(query_category_id)

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

            # EchoMem: Apply echo-based re-ranking boost
            echo_boost = 0.0
            metadata = memory.get("metadata", {})
            if use_echo_rerank and self.echo_config.enable_echo:
                echo_boost = self._calculate_echo_boost(query_lower, query_terms, metadata)
                combined = combined * (1 + echo_boost)

            # CategoryMem: Apply category-based re-ranking boost
            category_boost = 0.0
            memory_categories = set(memory.get("categories", []))
            if use_category_boost and self.category_processor and query_category_id:
                if query_category_id in memory_categories:
                    # Direct category match
                    category_boost = self.category_config.category_boost_weight
                elif memory_categories & related_category_ids:
                    # Related category match
                    category_boost = self.category_config.cross_category_boost
                combined = combined * (1 + category_boost)

            if boost_on_access:
                self.db.increment_access(memory["id"])
                self._check_promotion(memory["id"])
                # EchoMem: Re-echo on frequent access
                if (
                    self.echo_processor
                    and self.echo_config.reecho_on_access
                    and memory.get("access_count", 0) >= self.echo_config.reecho_threshold
                    and metadata.get("echo_depth") != "deep"
                ):
                    self._reecho_memory(memory["id"])

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
                    "echo_boost": echo_boost,
                    "category_boost": category_boost,
                }
            )

        # Persist category access updates
        if self.category_processor:
            self._persist_categories()

        results.sort(key=lambda x: x["composite_score"], reverse=True)
        return {"results": results[:limit]}

    def _calculate_echo_boost(
        self, query_lower: str, query_terms: set, metadata: Dict[str, Any]
    ) -> float:
        """Calculate re-ranking boost based on echo metadata matches."""
        boost = 0.0

        # Keyword match boost (each matching keyword adds 0.05)
        keywords = metadata.get("echo_keywords", [])
        if keywords:
            keyword_matches = sum(1 for kw in keywords if kw.lower() in query_lower)
            boost += keyword_matches * 0.05

        # Question form similarity boost (if query is similar to question_form)
        question_form = metadata.get("echo_question_form", "")
        if question_form:
            q_terms = set(question_form.lower().split())
            overlap = len(query_terms & q_terms)
            if overlap > 0:
                boost += min(0.15, overlap * 0.05)

        # Implication match boost
        implications = metadata.get("echo_implications", [])
        if implications:
            for impl in implications:
                impl_terms = set(impl.lower().split())
                if query_terms & impl_terms:
                    boost += 0.03

        # Cap boost at 0.3 (30% max increase)
        return min(0.3, boost)

    def _reecho_memory(self, memory_id: str) -> None:
        """Re-process a memory through deeper echo to strengthen it."""
        memory = self.db.get_memory(memory_id)
        if not memory or not self.echo_processor:
            return

        try:
            echo_result = self.echo_processor.reecho(memory)
            metadata = memory.get("metadata", {})
            metadata.update(echo_result.to_metadata())

            # Update memory with new echo data and boosted strength
            new_strength = min(1.0, memory.get("strength", 1.0) * 1.1)  # 10% boost
            self.db.update_memory(memory_id, {
                "metadata": metadata,
                "strength": new_strength,
            })
            self.db.log_event(memory_id, "REECHO", old_strength=memory.get("strength"), new_strength=new_strength)
        except Exception as e:
            logger.warning(f"Re-echo failed for memory {memory_id}: {e}")

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

        # EchoMem stats
        echo_stats = {"shallow": 0, "medium": 0, "deep": 0, "none": 0}
        for m in memories:
            metadata = m.get("metadata", {})
            depth = metadata.get("echo_depth", "none")
            if depth in echo_stats:
                echo_stats[depth] += 1
            else:
                echo_stats["none"] += 1

        return {
            "total": len(memories),
            "sml_count": sml_count,
            "lml_count": lml_count,
            "avg_strength": round(avg_strength, 3),
            "echo_stats": echo_stats,
            "echo_enabled": self.echo_config.enable_echo if self.echo_config else False,
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

    # CategoryMem methods
    def _persist_categories(self) -> None:
        """Persist category state to database."""
        if not self.category_processor:
            return
        categories = self.category_processor.get_all_categories()
        self.db.save_all_categories(categories)

    def get_categories(self) -> List[Dict[str, Any]]:
        """Get all categories."""
        if not self.category_processor:
            return []
        return self.category_processor.get_all_categories()

    def get_category(self, category_id: str) -> Optional[Dict[str, Any]]:
        """Get a specific category by ID."""
        if not self.category_processor:
            return None
        cat = self.category_processor.get_category(category_id)
        return cat.to_dict() if cat else None

    def get_category_summary(self, category_id: str, regenerate: bool = False) -> str:
        """
        Get or generate summary for a category.

        Args:
            category_id: Category ID
            regenerate: Force regenerate even if cached

        Returns:
            Summary text
        """
        if not self.category_processor:
            return ""

        cat = self.category_processor.get_category(category_id)
        if not cat:
            return "Category not found."

        # Return cached if available and not forcing regenerate
        if cat.summary and not regenerate:
            return cat.summary

        # Get memories in this category
        memories = self.db.get_memories_by_category(category_id, limit=20)

        return self.category_processor.generate_summary(category_id, memories)

    def get_all_summaries(self) -> Dict[str, str]:
        """
        Get summaries for all categories with memories.

        Returns category-level summaries with dynamic,
        evolving content based on stored memories.

        Returns:
            Dict mapping category name to summary
        """
        if not self.category_processor:
            return {}

        summaries = {}
        for cat in self.category_processor.categories.values():
            if cat.memory_count > 0:
                if not cat.summary:
                    memories = self.db.get_memories_by_category(cat.id, limit=20)
                    self.category_processor.generate_summary(cat.id, memories)
                summaries[cat.name] = cat.summary or f"{cat.memory_count} memories"

        self._persist_categories()
        return summaries

    def get_category_tree(self) -> List[Dict[str, Any]]:
        """
        Get hierarchical category tree.

        Returns:
            List of root categories with nested children
        """
        if not self.category_processor:
            return []

        def node_to_dict(node) -> Dict[str, Any]:
            return {
                "id": node.category.id,
                "name": node.category.name,
                "description": node.category.description,
                "memory_count": node.category.memory_count,
                "strength": node.category.strength,
                "depth": node.depth,
                "children": [node_to_dict(child) for child in node.children],
            }

        tree_nodes = self.category_processor.get_category_tree()
        return [node_to_dict(node) for node in tree_nodes]

    def apply_category_decay(self) -> Dict[str, Any]:
        """
        Apply decay to categories

        Unused categories weaken and may merge with similar ones.

        Returns:
            Stats about decayed/merged/deleted categories
        """
        if not self.category_processor or not self.category_config.enable_category_decay:
            return {"decayed": 0, "merged": 0, "deleted": 0}

        result = self.category_processor.apply_category_decay(
            decay_rate=self.category_config.category_decay_rate
        )

        self._persist_categories()
        return result

    def get_category_stats(self) -> Dict[str, Any]:
        """
        Get statistics about the category layer.

        Returns:
            Category statistics
        """
        if not self.category_processor:
            return {"enabled": False}

        stats = self.category_processor.get_category_stats()
        stats["enabled"] = True
        stats["config"] = {
            "auto_categorize": self.category_config.auto_categorize,
            "enable_decay": self.category_config.enable_category_decay,
            "boost_weight": self.category_config.category_boost_weight,
        }
        return stats

    def search_by_category(
        self,
        category_id: str,
        limit: int = 50,
        min_strength: float = 0.1,
    ) -> Dict[str, Any]:
        """
        Get memories in a specific category.

        Args:
            category_id: Category ID
            limit: Maximum results
            min_strength: Minimum memory strength

        Returns:
            Dict with results list
        """
        if not self.category_processor:
            return {"results": [], "category": None}

        cat = self.category_processor.get_category(category_id)
        if not cat:
            return {"results": [], "category": None, "error": "Category not found"}

        # Record access
        self.category_processor.access_category(category_id)

        memories = self.db.get_memories_by_category(
            category_id, limit=limit, min_strength=min_strength
        )

        self._persist_categories()

        return {
            "results": memories,
            "category": cat.to_dict(),
            "total": len(memories),
        }
