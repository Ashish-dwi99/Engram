"""Automatic cross-agent session bus for multi-lane handoff continuity."""

from __future__ import annotations

import logging
import json
from datetime import datetime, timezone

_UTC = timezone.utc
from typing import Any, Dict, List, Optional, Tuple

from engram.core.policy import ALL_CONFIDENTIALITY_SCOPES, DEFAULT_CAPABILITIES, HANDOFF_CAPABILITIES
from engram.utils.repo_identity import canonicalize_repo_identity

logger = logging.getLogger(__name__)
HANDOFF_SESSION_STATUSES = {"active", "paused", "completed", "abandoned"}


def _utc_now_iso() -> str:
    return datetime.now(tz=_UTC).isoformat()


def _safe_dt(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value))
    except Exception:
        return None


def _tokenize(text: Optional[str]) -> set[str]:
    if not text:
        return set()
    return {token.strip().lower() for token in str(text).replace("/", " ").replace("_", " ").split() if token.strip()}


def _merge_list_values(existing: Any, incoming: Any) -> List[str]:
    merged: List[str] = []
    for value in list(existing or []) + list(incoming or []):
        item = str(value).strip()
        if item and item not in merged:
            merged.append(item)
    return merged


def _stable_json(value: Any) -> str:
    try:
        return json.dumps(value, sort_keys=True, default=str)
    except Exception:
        return str(value)


class HandoffSessionBus:
    """Server-side session bus with lane routing and automatic checkpointing."""

    def __init__(
        self,
        *,
        db,
        memory=None,
        embedder=None,
        config: Optional[Dict[str, Any]] = None,
    ):
        self.db = db
        self.memory = memory
        self.embedder = embedder
        cfg = config or {}
        self.auto_enrich = bool(cfg.get("auto_enrich", True))
        self.max_sessions_per_user = int(cfg.get("max_sessions", 100))
        self.handoff_backend = str(cfg.get("handoff_backend", "hosted"))
        self.strict_handoff_auth = bool(cfg.get("strict_handoff_auth", True))
        self.allow_auto_trusted_bootstrap = bool(cfg.get("allow_auto_trusted_bootstrap", False))
        self.max_lanes_per_user = int(cfg.get("max_lanes_per_user", 50))
        self.max_checkpoints_per_lane = int(cfg.get("max_checkpoints_per_lane", 200))
        self.resume_statuses = self._normalize_status_list(
            cfg.get("resume_statuses", ["active", "paused"]),
            fallback=["active", "paused"],
        )
        self.lane_inactivity_minutes = int(cfg.get("lane_inactivity_minutes", 240))
        self.auto_trusted_agents = {
            str(agent).strip().lower()
            for agent in cfg.get(
                "auto_trusted_agents",
                ["pm", "design", "frontend", "backend", "claude-code", "codex", "chatgpt"],
            )
            if str(agent).strip()
        }

    # ------------------------------------------------------------------
    # Public API: automatic lane + checkpoints
    # ------------------------------------------------------------------

    def auto_resume_context(
        self,
        *,
        user_id: str,
        agent_id: Optional[str],
        repo_path: Optional[str] = None,
        branch: Optional[str] = None,
        lane_type: str = "general",
        objective: Optional[str] = None,
        agent_role: Optional[str] = None,
        namespace: str = "default",
        statuses: Optional[List[str]] = None,
        auto_create: bool = True,
    ) -> Dict[str, Any]:
        self._bootstrap_auto_trusted_policy(user_id=user_id, agent_id=agent_id, namespace=namespace)
        repo_identity = canonicalize_repo_identity(repo_path, branch=branch)
        allowed_statuses = self._normalize_status_list(statuses, fallback=list(self.resume_statuses))

        lane, created = self._select_or_create_lane(
            user_id=user_id,
            repo_identity=repo_identity,
            lane_type=lane_type,
            objective=objective,
            namespace=namespace,
            statuses=allowed_statuses,
            auto_create=auto_create,
        )
        if not lane:
            return {"error": "No matching lane found"}

        checkpoint = self.db.get_latest_handoff_checkpoint(lane["id"])
        packet = self._build_resume_packet(
            lane=lane,
            checkpoint=checkpoint,
            from_agent=agent_id,
            agent_role=agent_role,
        )
        packet["created_new_lane"] = bool(created)
        if created:
            packet["warm_context"] = self._warm_context(
                user_id=user_id,
                repo_identity=repo_identity,
                objective=objective,
            )
        return packet

    def auto_checkpoint(
        self,
        *,
        user_id: str,
        agent_id: str,
        payload: Dict[str, Any],
        event_type: str = "tool_complete",
        repo_path: Optional[str] = None,
        branch: Optional[str] = None,
        lane_id: Optional[str] = None,
        lane_type: str = "general",
        objective: Optional[str] = None,
        agent_role: Optional[str] = None,
        namespace: str = "default",
        confidentiality_scope: str = "work",
        expected_version: Optional[int] = None,
    ) -> Dict[str, Any]:
        self._bootstrap_auto_trusted_policy(user_id=user_id, agent_id=agent_id, namespace=namespace)
        repo_identity = canonicalize_repo_identity(repo_path, branch=branch)

        lane = self.db.get_handoff_lane(lane_id) if lane_id else None
        if lane and lane.get("user_id") != user_id:
            lane = None

        if not lane:
            lane, _ = self._select_or_create_lane(
                user_id=user_id,
                repo_identity=repo_identity,
                lane_type=lane_type,
                objective=objective,
                namespace=namespace,
                statuses=list(self.resume_statuses),
                auto_create=True,
            )
        if not lane:
            return {"error": "Unable to resolve or create handoff lane"}

        now = _utc_now_iso()
        normalized_payload = self._normalize_checkpoint_payload(payload)
        if objective and not normalized_payload.get("task_summary"):
            normalized_payload["task_summary"] = objective

        previous_state = dict(lane.get("current_state") or {})
        merged_state, conflicts = self._merge_state(previous_state, normalized_payload)

        checkpoint_data = {
            "lane_id": lane["id"],
            "user_id": user_id,
            "agent_id": agent_id,
            "agent_role": agent_role,
            "event_type": event_type,
            "task_summary": normalized_payload.get("task_summary"),
            "decisions_made": merged_state.get("decisions_made", []),
            "files_touched": merged_state.get("files_touched", []),
            "todos_remaining": merged_state.get("todos_remaining", []),
            "blockers": merged_state.get("blockers", []),
            "key_commands": merged_state.get("key_commands", []),
            "test_results": merged_state.get("test_results", []),
            "merge_conflicts": conflicts,
            "context_snapshot": merged_state.get("context_snapshot"),
            "created_at": now,
        }
        checkpoint_id = self.db.add_handoff_checkpoint(checkpoint_data)

        enrichment = {"linked_memories": 0, "linked_scenes": 0}
        if self.auto_enrich:
            enrichment = self._enrich_checkpoint(
                checkpoint_id=checkpoint_id,
                user_id=user_id,
                repo_identity=repo_identity,
                task_summary=merged_state.get("task_summary"),
                created_at=now,
            )

        target_version = int(lane.get("version", 0)) + 1
        persisted_version = target_version
        lane_status = str(normalized_payload.get("status") or lane.get("status") or "active")
        lane_updates = {
            "status": lane_status,
            "objective": merged_state.get("task_summary") or lane.get("objective"),
            "current_state": merged_state,
            "last_checkpoint_at": now,
            "version": target_version,
            "updated_at": now,
            "namespace": namespace or lane.get("namespace", "default"),
            "confidentiality_scope": confidentiality_scope or lane.get("confidentiality_scope", "work"),
            "repo_id": repo_identity.get("repo_id"),
            "repo_path": repo_identity.get("repo_path"),
            "branch": repo_identity.get("branch") or lane.get("branch"),
        }
        updated = self.db.update_handoff_lane(
            lane["id"],
            lane_updates,
            expected_version=expected_version,
        )
        if not updated:
            # Optimistic conflict fallback: refresh lane and force merge.
            fresh_lane = self.db.get_handoff_lane(lane["id"]) or lane
            fresh_state = dict(fresh_lane.get("current_state") or {})
            resolved_state, merge_conflicts = self._merge_state(fresh_state, normalized_payload)
            all_conflicts = self._dedupe_conflicts(list(conflicts) + list(merge_conflicts))
            self.db.update_handoff_lane(
                lane["id"],
                {
                    "current_state": resolved_state,
                    "version": int(fresh_lane.get("version", 0)) + 1,
                    "last_checkpoint_at": now,
                    "updated_at": now,
                    "status": lane_status,
                },
            )
            conflicts = all_conflicts
            merged_state = resolved_state
            persisted = self.db.get_handoff_lane(lane["id"])
            if persisted:
                persisted_version = int(persisted.get("version", persisted_version))
        else:
            persisted = self.db.get_handoff_lane(lane["id"])
            if persisted:
                persisted_version = int(persisted.get("version", persisted_version))

        if conflicts:
            self.db.add_handoff_lane_conflict(
                {
                    "lane_id": lane["id"],
                    "checkpoint_id": checkpoint_id,
                    "user_id": user_id,
                    "conflict_fields": [item.get("field") for item in conflicts if item.get("field")],
                    "previous_state": previous_state,
                    "incoming_state": normalized_payload,
                    "resolved_state": merged_state,
                    "created_at": now,
                }
            )

        self.db.prune_handoff_checkpoints(lane_id=lane["id"], max_checkpoints=self.max_checkpoints_per_lane)
        self.db.prune_handoff_lanes(user_id=user_id, max_lanes=self.max_lanes_per_user)

        return {
            "lane_id": lane["id"],
            "checkpoint_id": checkpoint_id,
            "status": lane_status,
            "version": persisted_version,
            "conflicts": conflicts,
            "enrichment": enrichment,
        }

    def finalize_lane(
        self,
        *,
        user_id: str,
        agent_id: str,
        lane_id: str,
        status: str = "paused",
        payload: Optional[Dict[str, Any]] = None,
        repo_path: Optional[str] = None,
        branch: Optional[str] = None,
        agent_role: Optional[str] = None,
        namespace: str = "default",
    ) -> Dict[str, Any]:
        normalized_status = self._normalize_status(status, default="paused")
        result = self.auto_checkpoint(
            user_id=user_id,
            agent_id=agent_id,
            lane_id=lane_id,
            payload=payload or {},
            event_type="agent_end",
            repo_path=repo_path,
            branch=branch,
            agent_role=agent_role,
            namespace=namespace,
        )
        lane = self.db.get_handoff_lane(lane_id)
        if lane:
            self.db.update_handoff_lane(lane_id, {"status": normalized_status})
        result["lane_status"] = normalized_status
        return result

    def list_lanes(
        self,
        *,
        user_id: str,
        repo_path: Optional[str] = None,
        status: Optional[str] = None,
        statuses: Optional[List[str]] = None,
        limit: int = 20,
    ) -> List[Dict[str, Any]]:
        repo_identity = canonicalize_repo_identity(repo_path, branch=None) if repo_path else {"repo_id": None}
        normalized_status = self._normalize_optional_status(status)
        normalized_statuses = (
            self._normalize_status_list(statuses, fallback=[], allow_empty=True)
            if statuses is not None
            else None
        )
        return self.db.list_handoff_lanes(
            user_id=user_id,
            repo_id=repo_identity.get("repo_id"),
            status=normalized_status,
            statuses=normalized_statuses,
            limit=limit,
        )

    # ------------------------------------------------------------------
    # Legacy compatibility (session digests)
    # ------------------------------------------------------------------

    def save_session_digest(self, user_id: str, agent_id: str, digest: Dict[str, Any]) -> Dict[str, Any]:
        repo_path = digest.get("repo")
        repo_identity = canonicalize_repo_identity(repo_path, branch=digest.get("branch"))
        status = self._normalize_status(digest.get("status"), default="paused")
        checkpoint_payload = {
            "status": status,
            "task_summary": digest.get("task_summary"),
            "decisions_made": digest.get("decisions_made", []),
            "files_touched": digest.get("files_touched", []),
            "todos_remaining": digest.get("todos_remaining", []),
            "blockers": digest.get("blockers", []),
            "key_commands": digest.get("key_commands", []),
            "test_results": digest.get("test_results", []),
            "context_snapshot": digest.get("context_snapshot"),
        }
        checkpoint = self.auto_checkpoint(
            user_id=user_id,
            agent_id=agent_id,
            payload=checkpoint_payload,
            event_type="agent_pause" if status in {"paused", "active"} else "agent_end",
            repo_path=repo_path,
            branch=digest.get("branch"),
            lane_id=digest.get("lane_id"),
            lane_type=digest.get("lane_type", "general"),
            objective=digest.get("task_summary"),
            agent_role=digest.get("agent_role"),
            namespace=digest.get("namespace", "default"),
            confidentiality_scope=digest.get("confidentiality_scope", "work"),
        )
        lane_id = checkpoint.get("lane_id")
        checkpoint_id = checkpoint.get("checkpoint_id")
        checkpoint_memories = self.db.get_handoff_checkpoint_memories(checkpoint_id) if checkpoint_id else []
        checkpoint_scenes = self.db.get_handoff_checkpoint_scenes(checkpoint_id) if checkpoint_id else []

        now = _utc_now_iso()
        session_data = {
            "user_id": user_id,
            "agent_id": agent_id,
            "repo": repo_identity.get("repo_path"),
            "repo_id": repo_identity.get("repo_id"),
            "status": status,
            "task_summary": digest.get("task_summary", ""),
            "decisions_made": digest.get("decisions_made", []),
            "files_touched": digest.get("files_touched", []),
            "todos_remaining": digest.get("todos_remaining", []),
            "blockers": digest.get("blockers", []),
            "key_commands": digest.get("key_commands", []),
            "test_results": digest.get("test_results", []),
            "context_snapshot": digest.get("context_snapshot"),
            "linked_memory_ids": [item.get("id") for item in checkpoint_memories if item.get("id")],
            "linked_scene_ids": [item.get("id") for item in checkpoint_scenes if item.get("id")],
            "lane_id": lane_id,
            "started_at": digest.get("started_at", now),
            "ended_at": digest.get("ended_at"),
            "last_checkpoint_at": now,
            "namespace": digest.get("namespace", "default"),
            "confidentiality_scope": digest.get("confidentiality_scope", "work"),
        }
        session_id = self.db.add_handoff_session(session_data)
        self.db.prune_handoff_sessions(user_id=user_id, max_sessions=self.max_sessions_per_user)
        return self.db.get_handoff_session(session_id) or {"id": session_id, **session_data}

    def get_handoff_context(self, session_id: str) -> Dict[str, Any]:
        session = self.db.get_handoff_session(session_id)
        if not session:
            return {"error": "Session not found"}
        lane = self.db.get_handoff_lane(session.get("lane_id")) if session.get("lane_id") else None
        checkpoint = self.db.get_latest_handoff_checkpoint(session.get("lane_id")) if session.get("lane_id") else None

        related_memories = self.db.get_handoff_session_memories(session_id)
        if not related_memories and checkpoint:
            related_memories = self.db.get_handoff_checkpoint_memories(checkpoint["id"])
        related_scenes = self.db.get_handoff_checkpoint_scenes(checkpoint["id"]) if checkpoint else []

        return {
            "session_id": session["id"],
            "lane_id": session.get("lane_id"),
            "status": session.get("status", "paused"),
            "repo": session.get("repo"),
            "repo_id": session.get("repo_id"),
            "from_agent": session.get("agent_id"),
            "task_summary": session.get("task_summary", ""),
            "decisions_made": session.get("decisions_made", []),
            "files_touched": session.get("files_touched", []),
            "todos_remaining": session.get("todos_remaining", []),
            "blockers": session.get("blockers", []),
            "key_commands": session.get("key_commands", []),
            "test_results": session.get("test_results", []),
            "context_snapshot": session.get("context_snapshot"),
            "started_at": session.get("started_at"),
            "ended_at": session.get("ended_at"),
            "last_checkpoint_at": session.get("last_checkpoint_at"),
            "lane_status": lane.get("status") if lane else None,
            "lane_version": lane.get("version") if lane else None,
            "related_memories": [
                {"id": item.get("id"), "memory": item.get("memory", "")}
                for item in related_memories
            ],
            "related_scenes": [
                {
                    "id": scene.get("id"),
                    "summary": scene.get("summary"),
                    "topic": scene.get("topic"),
                    "start_time": scene.get("start_time"),
                }
                for scene in related_scenes
            ],
        }

    def get_last_session(
        self,
        *,
        user_id: str,
        agent_id: Optional[str] = None,
        repo: Optional[str] = None,
        statuses: Optional[List[str]] = None,
    ) -> Optional[Dict[str, Any]]:
        repo_identity = canonicalize_repo_identity(repo, branch=None) if repo else {"repo_id": None}
        preferred_statuses = self._normalize_status_list(statuses, fallback=list(self.resume_statuses))
        repo_candidates: List[Optional[str]] = [repo_identity.get("repo_id")]
        if repo_candidates[0] is not None:
            repo_candidates.append(None)

        for repo_id in repo_candidates:
            session = self.db.get_last_handoff_session(
                user_id=user_id,
                agent_id=agent_id,
                repo=repo if repo_id is not None else None,
                repo_id=repo_id,
                statuses=preferred_statuses,
            )
            if session:
                return self.get_handoff_context(session["id"])

        # Compatibility fallback: if preferred-status legacy sessions are absent,
        # derive context from active lane/checkpoint state before broadening status.
        for repo_id in repo_candidates:
            lane_packet = self._latest_lane_resume_packet(
                user_id=user_id,
                agent_id=agent_id,
                repo_id=repo_id,
                statuses=preferred_statuses,
            )
            if lane_packet:
                return lane_packet

        # Historical fallback is only used for default behavior. If callers pass
        # explicit statuses, respect that filter strictly.
        if statuses is not None:
            return None

        for repo_id in repo_candidates:
            session = self.db.get_last_handoff_session(
                user_id=user_id,
                agent_id=agent_id,
                repo=repo if repo_id is not None else None,
                repo_id=repo_id,
                statuses=None,
            )
            if session:
                return self.get_handoff_context(session["id"])

        for repo_id in repo_candidates:
            lane_packet = self._latest_lane_resume_packet(
                user_id=user_id,
                agent_id=agent_id,
                repo_id=repo_id,
                statuses=None,
            )
            if lane_packet:
                return lane_packet
        return None

    def list_sessions(
        self,
        *,
        user_id: str,
        agent_id: Optional[str] = None,
        repo: Optional[str] = None,
        status: Optional[str] = None,
        statuses: Optional[List[str]] = None,
        limit: int = 20,
    ) -> List[Dict[str, Any]]:
        repo_identity = canonicalize_repo_identity(repo, branch=None) if repo else {"repo_id": None}
        normalized_status = self._normalize_optional_status(status)
        normalized_statuses = (
            self._normalize_status_list(statuses, fallback=[], allow_empty=True)
            if statuses is not None
            else None
        )
        sessions = self.db.list_handoff_sessions(
            user_id=user_id,
            agent_id=agent_id,
            repo=repo,
            repo_id=repo_identity.get("repo_id"),
            status=normalized_status,
            statuses=normalized_statuses,
            limit=limit,
        )
        if sessions:
            return sessions

        lane_sessions = self._lane_sessions_fallback(
            user_id=user_id,
            agent_id=agent_id,
            repo_id=repo_identity.get("repo_id"),
            status=normalized_status,
            statuses=normalized_statuses,
            limit=limit,
        )
        if lane_sessions or repo_identity.get("repo_id") is None:
            return lane_sessions
        return self._lane_sessions_fallback(
            user_id=user_id,
            agent_id=agent_id,
            repo_id=None,
            status=normalized_status,
            statuses=normalized_statuses,
            limit=limit,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    # Cache bootstrapped policies to avoid a DB query on every checkpoint/resume.
    _bootstrapped_policies: set = set()

    def _bootstrap_auto_trusted_policy(self, *, user_id: str, agent_id: Optional[str], namespace: str) -> None:
        if not self.allow_auto_trusted_bootstrap:
            return
        if not user_id or not agent_id:
            return
        normalized_agent = str(agent_id).strip().lower()
        if normalized_agent not in self.auto_trusted_agents:
            return
        cache_key = f"{user_id}::{normalized_agent}"
        if cache_key in self._bootstrapped_policies:
            return
        existing = self.db.get_agent_policy(
            user_id=user_id,
            agent_id=agent_id,
            include_wildcard=False,
        )
        if existing:
            self._bootstrapped_policies.add(cache_key)
            return
        capabilities = sorted(set(list(DEFAULT_CAPABILITIES) + list(HANDOFF_CAPABILITIES)))
        namespaces = ["default"]
        ns_value = str(namespace or "").strip()
        if ns_value and ns_value not in namespaces:
            namespaces.append(ns_value)
        self.db.upsert_agent_policy(
            user_id=user_id,
            agent_id=agent_id,
            allowed_confidentiality_scopes=list(ALL_CONFIDENTIALITY_SCOPES),
            allowed_capabilities=capabilities,
            allowed_namespaces=namespaces,
        )
        self._bootstrapped_policies.add(cache_key)

    @staticmethod
    def _normalize_status(value: Optional[str], *, default: str) -> str:
        normalized = str(value or "").strip().lower()
        if normalized in HANDOFF_SESSION_STATUSES:
            return normalized
        return default

    @staticmethod
    def _normalize_optional_status(value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        normalized = str(value).strip().lower()
        if normalized in HANDOFF_SESSION_STATUSES:
            return normalized
        raise ValueError(
            "Invalid handoff status: "
            f"{value!r}. Allowed: {', '.join(sorted(HANDOFF_SESSION_STATUSES))}"
        )

    @staticmethod
    def _normalize_status_list(
        values: Optional[List[str]],
        *,
        fallback: List[str],
        allow_empty: bool = False,
    ) -> List[str]:
        if values is None:
            return list(fallback)

        raw_values: List[str]
        if isinstance(values, str):
            raw_values = [v for v in values.split(",")]
        else:
            raw_values = [str(v) for v in values]

        normalized: List[str] = []
        invalid: List[str] = []
        for value in raw_values:
            item = str(value).strip().lower()
            if not item:
                continue
            if item not in HANDOFF_SESSION_STATUSES:
                invalid.append(item)
                continue
            if item not in normalized:
                normalized.append(item)

        if invalid:
            bad = ", ".join(sorted(set(invalid)))
            allowed = ", ".join(sorted(HANDOFF_SESSION_STATUSES))
            raise ValueError(f"Invalid handoff statuses: {bad}. Allowed: {allowed}")

        if normalized:
            return normalized
        if allow_empty:
            return []
        return list(fallback)

    @staticmethod
    def _dedupe_conflicts(conflicts: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        deduped: List[Dict[str, Any]] = []
        seen = set()
        for conflict in conflicts:
            key = (
                conflict.get("field"),
                _stable_json(conflict.get("previous")),
                _stable_json(conflict.get("incoming")),
            )
            if key in seen:
                continue
            seen.add(key)
            deduped.append(conflict)
        return deduped

    def _latest_lane_resume_packet(
        self,
        *,
        user_id: str,
        agent_id: Optional[str],
        repo_id: Optional[str],
        statuses: Optional[List[str]],
    ) -> Optional[Dict[str, Any]]:
        lanes = self.db.list_handoff_lanes(
            user_id=user_id,
            repo_id=repo_id,
            statuses=statuses,
            limit=50,
        )
        for lane in lanes:
            checkpoint = self.db.get_latest_handoff_checkpoint(lane["id"])
            source_agent = checkpoint.get("agent_id") if checkpoint else None
            if agent_id and source_agent != agent_id:
                continue
            return self._build_resume_packet(
                lane=lane,
                checkpoint=checkpoint,
                from_agent=source_agent,
                agent_role=checkpoint.get("agent_role") if checkpoint else None,
            )
        return None

    def _lane_sessions_fallback(
        self,
        *,
        user_id: str,
        agent_id: Optional[str],
        repo_id: Optional[str],
        status: Optional[str],
        statuses: Optional[List[str]],
        limit: int,
    ) -> List[Dict[str, Any]]:
        lanes = self.db.list_handoff_lanes(
            user_id=user_id,
            repo_id=repo_id,
            status=status,
            statuses=statuses,
            limit=max(limit, 1),
        )
        results: List[Dict[str, Any]] = []
        for lane in lanes:
            checkpoint = self.db.get_latest_handoff_checkpoint(lane["id"])
            source_agent = checkpoint.get("agent_id") if checkpoint else None
            if agent_id and source_agent != agent_id:
                continue
            source = checkpoint or lane.get("current_state") or {}
            results.append(
                {
                    "id": lane.get("id"),
                    "agent_id": source_agent,
                    "repo": lane.get("repo_path"),
                    "repo_id": lane.get("repo_id"),
                    "status": lane.get("status"),
                    "task_summary": source.get("task_summary") or lane.get("objective", ""),
                    "decisions_made": source.get("decisions_made", []),
                    "files_touched": source.get("files_touched", []),
                    "todos_remaining": source.get("todos_remaining", []),
                    "blockers": source.get("blockers", []),
                    "key_commands": source.get("key_commands", []),
                    "test_results": source.get("test_results", []),
                    "context_snapshot": source.get("context_snapshot"),
                    "lane_id": lane.get("id"),
                    "last_checkpoint_at": lane.get("last_checkpoint_at"),
                    "updated_at": lane.get("updated_at"),
                    "source": "lane_checkpoint",
                }
            )
            if len(results) >= limit:
                break
        return results

    def _select_or_create_lane(
        self,
        *,
        user_id: str,
        repo_identity: Dict[str, Optional[str]],
        lane_type: str,
        objective: Optional[str],
        namespace: str,
        statuses: List[str],
        auto_create: bool,
    ) -> Tuple[Optional[Dict[str, Any]], bool]:
        candidates = self.db.list_handoff_lanes(
            user_id=user_id,
            repo_id=repo_identity.get("repo_id"),
            statuses=statuses,
            limit=50,
        )
        if not candidates:
            candidates = self.db.list_handoff_lanes(
                user_id=user_id,
                repo_id=None,
                statuses=statuses,
                limit=50,
            )

        best_lane: Optional[Dict[str, Any]] = None
        best_score = -1.0
        objective_terms = _tokenize(objective)
        for lane in candidates:
            score = self._score_lane(
                lane=lane,
                repo_id=repo_identity.get("repo_id"),
                branch=repo_identity.get("branch"),
                objective_terms=objective_terms,
            )
            if score > best_score:
                best_score = score
                best_lane = lane

        if best_lane and best_score >= 0.45:
            return best_lane, False
        if not auto_create:
            return None, False

        now = _utc_now_iso()
        lane_id = self.db.add_handoff_lane(
            {
                "user_id": user_id,
                "repo_id": repo_identity.get("repo_id"),
                "repo_path": repo_identity.get("repo_path"),
                "branch": repo_identity.get("branch"),
                "lane_type": lane_type or "general",
                "status": "active",
                "objective": objective,
                "current_state": {
                    "task_summary": objective or "",
                    "decisions_made": [],
                    "files_touched": [],
                    "todos_remaining": [],
                    "blockers": [],
                    "key_commands": [],
                    "test_results": [],
                    "context_snapshot": None,
                },
                "namespace": namespace or "default",
                "confidentiality_scope": "work",
                "last_checkpoint_at": now,
                "version": 0,
                "created_at": now,
                "updated_at": now,
            }
        )
        lane = self.db.get_handoff_lane(lane_id)
        return lane, True

    def _score_lane(
        self,
        *,
        lane: Dict[str, Any],
        repo_id: Optional[str],
        branch: Optional[str],
        objective_terms: set[str],
    ) -> float:
        score = 0.0
        if repo_id and lane.get("repo_id") == repo_id:
            score += 0.55
        if branch and lane.get("branch") == branch:
            score += 0.15

        lane_terms = _tokenize(lane.get("objective"))
        if objective_terms and lane_terms:
            overlap = len(objective_terms & lane_terms) / max(1, len(objective_terms | lane_terms))
            score += overlap * 0.2

        last_checkpoint = _safe_dt(lane.get("last_checkpoint_at") or lane.get("updated_at") or lane.get("created_at"))
        if last_checkpoint:
            now = datetime.now(tz=_UTC)
            # Ensure last_checkpoint is offset-aware for comparison.
            if last_checkpoint.tzinfo is None:
                last_checkpoint = last_checkpoint.replace(tzinfo=_UTC)
            age_minutes = max(0.0, (now - last_checkpoint).total_seconds() / 60.0)
            score += max(0.0, 0.1 - min(age_minutes, 24 * 60) / (24 * 60 * 10))
            if age_minutes > self.lane_inactivity_minutes and lane.get("status") == "active":
                score -= 0.2
        return score

    def _normalize_checkpoint_payload(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        payload = dict(payload or {})
        normalized = {
            "status": self._normalize_status(payload.get("status"), default="active"),
            "task_summary": str(payload.get("task_summary") or "").strip(),
            "decisions_made": _merge_list_values([], payload.get("decisions_made", [])),
            "files_touched": _merge_list_values([], payload.get("files_touched", [])),
            "todos_remaining": _merge_list_values([], payload.get("todos_remaining", [])),
            "blockers": _merge_list_values([], payload.get("blockers", [])),
            "key_commands": _merge_list_values([], payload.get("key_commands", [])),
            "test_results": _merge_list_values([], payload.get("test_results", [])),
            "context_snapshot": payload.get("context_snapshot"),
        }
        return normalized

    def _merge_state(self, current: Dict[str, Any], incoming: Dict[str, Any]) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
        merged = dict(current or {})
        conflicts: List[Dict[str, Any]] = []
        list_fields = {
            "decisions_made",
            "files_touched",
            "todos_remaining",
            "blockers",
            "key_commands",
            "test_results",
        }
        scalar_fields = {"task_summary", "context_snapshot", "status"}

        for key in list_fields:
            merged[key] = _merge_list_values(merged.get(key, []), incoming.get(key, []))

        for key in scalar_fields:
            old_value = merged.get(key)
            new_value = incoming.get(key)
            if new_value in (None, "", []):
                continue
            if old_value not in (None, "", []) and old_value != new_value:
                conflicts.append({"field": key, "previous": old_value, "incoming": new_value})
            merged[key] = new_value
        return merged, conflicts

    def _warm_context(
        self,
        *,
        user_id: str,
        repo_identity: Dict[str, Optional[str]],
        objective: Optional[str],
    ) -> Dict[str, Any]:
        memories: List[Dict[str, Any]] = []
        try:
            if self.memory and objective:
                search_payload = self.memory.search(
                    query=objective,
                    user_id=user_id,
                    limit=6,
                    boost_on_access=False,
                )
                memories = list(search_payload.get("results", []))
            if not memories:
                all_payload = self.memory.get_all(user_id=user_id, limit=6) if self.memory else {"results": []}
                memories = list(all_payload.get("results", []))
        except Exception:
            logger.warning("Warm context memory lookup failed", exc_info=True)
            memories = []

        scenes = self.db.get_scenes(user_id=user_id, limit=5)
        repo_path = (repo_identity.get("repo_path") or "").lower()
        if repo_path:
            scoped = [scene for scene in scenes if repo_path in str(scene.get("location") or "").lower()]
            if scoped:
                scenes = scoped

        return {
            "related_memories": [
                {"id": memory.get("id"), "memory": memory.get("memory", "")}
                for memory in memories[:6]
            ],
            "related_scenes": [
                {
                    "id": scene.get("id"),
                    "summary": scene.get("summary"),
                    "topic": scene.get("topic"),
                    "start_time": scene.get("start_time"),
                }
                for scene in scenes[:5]
            ],
        }

    def _enrich_checkpoint(
        self,
        *,
        checkpoint_id: str,
        user_id: str,
        repo_identity: Dict[str, Optional[str]],
        task_summary: Optional[str],
        created_at: str,
    ) -> Dict[str, int]:
        linked_memory_ids: List[str] = []
        linked_scene_ids: List[str] = []
        query = (task_summary or "").strip()

        if query and self.memory and self.memory.embedder and self.memory.vector_store:
            try:
                embedding = self.memory.embedder.embed(query, memory_action="search")
                results = self.memory.vector_store.search(
                    query=query,
                    vectors=embedding,
                    limit=12,
                    filters={"user_id": user_id},
                )
                for item in results:
                    memory_id = getattr(item, "id", None)
                    if memory_id is None and isinstance(item, dict):
                        memory_id = item.get("id")
                    if memory_id and memory_id not in linked_memory_ids:
                        linked_memory_ids.append(str(memory_id))
            except Exception:
                logger.warning("Handoff vector enrichment failed", exc_info=True)

        if not linked_memory_ids and query:
            query_terms = _tokenize(query)
            all_memories = self.db.get_all_memories(user_id=user_id, include_tombstoned=False)
            scored: List[Tuple[int, str]] = []
            for memory in all_memories:
                memory_text = str(memory.get("memory", "")).lower()
                overlap = sum(1 for token in query_terms if token in memory_text)
                if overlap > 0:
                    scored.append((overlap, str(memory["id"])))
            scored.sort(key=lambda item: item[0], reverse=True)
            linked_memory_ids = [memory_id for _, memory_id in scored[:10]]

        scenes = self.db.get_scenes(
            user_id=user_id,
            start_before=created_at,
            limit=10,
        )
        repo_path = (repo_identity.get("repo_path") or "").lower()
        if repo_path:
            scoped_scenes = [scene for scene in scenes if repo_path in str(scene.get("location") or "").lower()]
            if scoped_scenes:
                scenes = scoped_scenes
        linked_scene_ids = [str(scene["id"]) for scene in scenes[:6] if scene.get("id")]

        for index, memory_id in enumerate(linked_memory_ids[:10]):
            self.db.add_handoff_checkpoint_memory(
                checkpoint_id=checkpoint_id,
                memory_id=memory_id,
                relevance_score=max(0.1, 1.0 - (index * 0.05)),
            )
        for index, scene_id in enumerate(linked_scene_ids[:6]):
            self.db.add_handoff_checkpoint_scene(
                checkpoint_id=checkpoint_id,
                scene_id=scene_id,
                relevance_score=max(0.1, 1.0 - (index * 0.05)),
            )

        return {
            "linked_memories": min(10, len(linked_memory_ids)),
            "linked_scenes": min(6, len(linked_scene_ids)),
        }

    def _build_resume_packet(
        self,
        *,
        lane: Dict[str, Any],
        checkpoint: Optional[Dict[str, Any]],
        from_agent: Optional[str],
        agent_role: Optional[str],
    ) -> Dict[str, Any]:
        state = dict(lane.get("current_state") or {})
        source = checkpoint or state
        memories = self.db.get_handoff_checkpoint_memories(checkpoint["id"]) if checkpoint else []
        scenes = self.db.get_handoff_checkpoint_scenes(checkpoint["id"]) if checkpoint else []
        return {
            "lane_id": lane.get("id"),
            "repo_id": lane.get("repo_id"),
            "repo_path": lane.get("repo_path"),
            "branch": lane.get("branch"),
            "lane_type": lane.get("lane_type"),
            "status": lane.get("status"),
            "objective": lane.get("objective"),
            "lane_version": lane.get("version", 0),
            "from_agent": checkpoint.get("agent_id") if checkpoint else from_agent,
            "agent_role": checkpoint.get("agent_role") if checkpoint else agent_role,
            "task_summary": source.get("task_summary", lane.get("objective", "")),
            "decisions_made": source.get("decisions_made", []),
            "files_touched": source.get("files_touched", []),
            "todos_remaining": source.get("todos_remaining", []),
            "blockers": source.get("blockers", []),
            "key_commands": source.get("key_commands", []),
            "test_results": source.get("test_results", []),
            "context_snapshot": source.get("context_snapshot"),
            "last_checkpoint_at": lane.get("last_checkpoint_at"),
            "next_actions": source.get("todos_remaining", []),
            "related_memories": [
                {"id": item.get("id"), "memory": item.get("memory", "")}
                for item in memories
            ],
            "related_scenes": [
                {
                    "id": scene.get("id"),
                    "summary": scene.get("summary"),
                    "topic": scene.get("topic"),
                    "start_time": scene.get("start_time"),
                }
                for scene in scenes
            ],
        }
