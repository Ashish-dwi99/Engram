"""Compatibility layer for cross-agent handoff powered by HandoffSessionBus."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from engram.core.handoff_bus import HandoffSessionBus


class HandoffProcessor:
    """Backwards-compatible handoff facade with session bus internals."""

    def __init__(
        self,
        db,
        memory=None,
        embedder=None,
        llm=None,  # retained for compatibility
        config: Optional[Dict[str, Any]] = None,
    ):
        self.db = db
        self.memory = memory
        self.embedder = embedder
        cfg = config or {}
        self.auto_enrich = bool(cfg.get("auto_enrich", True))
        self.max_sessions = int(cfg.get("max_sessions", 100))
        self.session_bus = HandoffSessionBus(
            db=db,
            memory=memory,
            embedder=embedder,
            config=cfg,
        )

    # ------------------------------------------------------------------
    # Legacy session digest API
    # ------------------------------------------------------------------

    def save_digest(self, user_id: str, agent_id: str, digest: Dict[str, Any]) -> Dict[str, Any]:
        return self.session_bus.save_session_digest(user_id=user_id, agent_id=agent_id, digest=digest)

    def get_handoff_context(self, session_id: str) -> Dict[str, Any]:
        return self.session_bus.get_handoff_context(session_id)

    def get_last_session(
        self,
        *,
        user_id: str,
        agent_id: Optional[str] = None,
        repo: Optional[str] = None,
        statuses: Optional[List[str]] = None,
    ) -> Optional[Dict[str, Any]]:
        return self.session_bus.get_last_session(
            user_id=user_id,
            agent_id=agent_id,
            repo=repo,
            statuses=statuses,
        )

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
        return self.session_bus.list_sessions(
            user_id=user_id,
            agent_id=agent_id,
            repo=repo,
            status=status,
            statuses=statuses,
            limit=limit,
        )

    # ------------------------------------------------------------------
    # Session bus API
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
        return self.session_bus.auto_resume_context(
            user_id=user_id,
            agent_id=agent_id,
            repo_path=repo_path,
            branch=branch,
            lane_type=lane_type,
            objective=objective,
            agent_role=agent_role,
            namespace=namespace,
            statuses=statuses,
            auto_create=auto_create,
        )

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
        return self.session_bus.auto_checkpoint(
            user_id=user_id,
            agent_id=agent_id,
            payload=payload,
            event_type=event_type,
            repo_path=repo_path,
            branch=branch,
            lane_id=lane_id,
            lane_type=lane_type,
            objective=objective,
            agent_role=agent_role,
            namespace=namespace,
            confidentiality_scope=confidentiality_scope,
            expected_version=expected_version,
        )

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
        return self.session_bus.finalize_lane(
            user_id=user_id,
            agent_id=agent_id,
            lane_id=lane_id,
            status=status,
            payload=payload,
            repo_path=repo_path,
            branch=branch,
            agent_role=agent_role,
            namespace=namespace,
        )

    def list_lanes(
        self,
        *,
        user_id: str,
        repo_path: Optional[str] = None,
        status: Optional[str] = None,
        statuses: Optional[List[str]] = None,
        limit: int = 20,
    ) -> List[Dict[str, Any]]:
        return self.session_bus.list_lanes(
            user_id=user_id,
            repo_path=repo_path,
            status=status,
            statuses=statuses,
            limit=limit,
        )

    # Legacy method kept for callers that still invoke explicit enrichment.
    def enrich(self, session_id: str, user_id: str) -> Dict[str, Any]:
        session = self.db.get_handoff_session(session_id)
        if not session:
            return {}
        return {
            "linked_memories": len(session.get("linked_memory_ids", [])),
            "linked_scenes": len(session.get("linked_scene_ids", [])),
        }

