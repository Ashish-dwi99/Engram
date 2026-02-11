"""Handoff backend adapters for local and hosted continuity paths."""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

from engram.memory.client import MemoryClient


class HandoffBackendError(RuntimeError):
    """Structured handoff backend error."""

    def __init__(self, code: str, message: str):
        self.code = str(code)
        self.message = str(message)
        super().__init__(self.message)

    def to_dict(self) -> Dict[str, str]:
        return {"code": self.code, "message": self.message}


def classify_handoff_error(exc: Exception) -> HandoffBackendError:
    message = str(exc).strip() or exc.__class__.__name__
    lowered = message.lower()

    if "missing required capability" in lowered or "not allowed by policy" in lowered:
        return HandoffBackendError("missing_capability", message)
    if "capability token required" in lowered or "invalid capability token" in lowered or "session expired" in lowered:
        return HandoffBackendError("missing_or_expired_token", message)
    if " 401" in lowered or " 403" in lowered or "unauthorized" in lowered or "forbidden" in lowered:
        return HandoffBackendError("missing_or_expired_token", message)
    if "connection" in lowered or "timed out" in lowered or "max retries exceeded" in lowered:
        return HandoffBackendError("hosted_backend_unavailable", message)
    if "no matching lane found" in lowered or "unable to resolve or create handoff lane" in lowered:
        return HandoffBackendError("lane_resolution_failed", message)
    return HandoffBackendError("handoff_error", message)


class LocalHandoffBackend:
    """Handoff adapter using in-process Memory APIs."""

    def __init__(self, memory):
        self.memory = memory

    def _session_token(
        self,
        *,
        user_id: str,
        requester_agent_id: Optional[str],
        capabilities: List[str],
        namespace: str,
    ) -> str:
        try:
            session = self.memory.create_session(
                user_id=user_id,
                agent_id=requester_agent_id,
                allowed_confidentiality_scopes=["work", "personal", "finance", "health", "private"],
                capabilities=capabilities,
                namespaces=[namespace],
                ttl_minutes=24 * 60,
            )
        except Exception as exc:
            raise classify_handoff_error(exc) from exc
        token = session.get("token")
        if not token:
            raise HandoffBackendError("missing_or_expired_token", "Session token was not issued")
        return token

    def save_session_digest(
        self,
        *,
        user_id: str,
        agent_id: str,
        requester_agent_id: str,
        namespace: str,
        digest: Dict[str, Any],
    ) -> Dict[str, Any]:
        token = self._session_token(
            user_id=user_id,
            requester_agent_id=requester_agent_id,
            capabilities=["write_handoff"],
            namespace=namespace,
        )
        try:
            return self.memory.save_session_digest(
                user_id,
                agent_id,
                digest,
                token=token,
                requester_agent_id=requester_agent_id,
            )
        except Exception as exc:
            raise classify_handoff_error(exc) from exc

    def get_last_session(
        self,
        *,
        user_id: str,
        agent_id: Optional[str],
        requester_agent_id: str,
        namespace: str,
        repo: Optional[str],
        statuses: Optional[List[str]] = None,
    ) -> Optional[Dict[str, Any]]:
        token = self._session_token(
            user_id=user_id,
            requester_agent_id=requester_agent_id,
            capabilities=["read_handoff"],
            namespace=namespace,
        )
        try:
            return self.memory.get_last_session(
                user_id,
                agent_id=agent_id,
                repo=repo,
                statuses=statuses,
                token=token,
                requester_agent_id=requester_agent_id,
            )
        except Exception as exc:
            raise classify_handoff_error(exc) from exc

    def list_sessions(
        self,
        *,
        user_id: str,
        agent_id: Optional[str],
        requester_agent_id: str,
        namespace: str,
        repo: Optional[str],
        status: Optional[str],
        statuses: Optional[List[str]],
        limit: int,
    ) -> List[Dict[str, Any]]:
        token = self._session_token(
            user_id=user_id,
            requester_agent_id=requester_agent_id,
            capabilities=["read_handoff"],
            namespace=namespace,
        )
        try:
            return self.memory.list_sessions(
                user_id=user_id,
                agent_id=agent_id,
                repo=repo,
                status=status,
                statuses=statuses,
                limit=limit,
                token=token,
                requester_agent_id=requester_agent_id,
            )
        except Exception as exc:
            raise classify_handoff_error(exc) from exc

    def auto_resume_context(
        self,
        *,
        user_id: str,
        agent_id: str,
        namespace: str,
        repo_path: str,
        branch: Optional[str],
        lane_type: str,
        objective: str,
        agent_role: Optional[str],
        statuses: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        token = self._session_token(
            user_id=user_id,
            requester_agent_id=agent_id,
            capabilities=["read_handoff"],
            namespace=namespace,
        )
        try:
            return self.memory.auto_resume_context(
                user_id=user_id,
                agent_id=agent_id,
                repo_path=repo_path,
                branch=branch,
                lane_type=lane_type,
                objective=objective,
                agent_role=agent_role,
                namespace=namespace,
                statuses=statuses,
                token=token,
                requester_agent_id=agent_id,
                auto_create=True,
            )
        except Exception as exc:
            raise classify_handoff_error(exc) from exc

    def auto_checkpoint(
        self,
        *,
        user_id: str,
        agent_id: str,
        namespace: str,
        repo_path: str,
        branch: Optional[str],
        lane_id: Optional[str],
        lane_type: str,
        objective: str,
        agent_role: Optional[str],
        confidentiality_scope: str,
        payload: Dict[str, Any],
        event_type: str,
    ) -> Dict[str, Any]:
        token = self._session_token(
            user_id=user_id,
            requester_agent_id=agent_id,
            capabilities=["write_handoff"],
            namespace=namespace,
        )
        try:
            return self.memory.auto_checkpoint(
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
                token=token,
                requester_agent_id=agent_id,
            )
        except Exception as exc:
            raise classify_handoff_error(exc) from exc


class HostedHandoffBackend:
    """Handoff adapter using hosted Engram REST APIs."""

    def __init__(self, api_url: str):
        host = str(api_url).strip()
        if not host:
            raise HandoffBackendError("hosted_backend_unavailable", "ENGRAM_API_URL is not configured")
        self.client = MemoryClient(
            host=host,
            api_key=os.environ.get("ENGRAM_API_KEY"),
            org_id=os.environ.get("ENGRAM_ORG_ID"),
            project_id=os.environ.get("ENGRAM_PROJECT_ID"),
            admin_key=os.environ.get("ENGRAM_ADMIN_KEY"),
        )

    def _session_token(
        self,
        *,
        user_id: str,
        requester_agent_id: Optional[str],
        capabilities: List[str],
        namespace: str,
    ) -> str:
        try:
            session = self.client.create_session(
                user_id=user_id,
                agent_id=requester_agent_id,
                allowed_confidentiality_scopes=["work", "personal", "finance", "health", "private"],
                capabilities=capabilities,
                namespaces=[namespace],
                ttl_minutes=24 * 60,
            )
        except Exception as exc:
            raise classify_handoff_error(exc) from exc
        token = session.get("token")
        if not token:
            raise HandoffBackendError("missing_or_expired_token", "Session token was not issued")
        return token

    def save_session_digest(
        self,
        *,
        user_id: str,
        agent_id: str,
        requester_agent_id: str,
        namespace: str,
        digest: Dict[str, Any],
    ) -> Dict[str, Any]:
        self._session_token(
            user_id=user_id,
            requester_agent_id=requester_agent_id,
            capabilities=["write_handoff"],
            namespace=namespace,
        )
        payload = dict(digest)
        payload["user_id"] = user_id
        payload["agent_id"] = agent_id
        payload["requester_agent_id"] = requester_agent_id
        try:
            return self.client.save_session_digest(**payload)
        except Exception as exc:
            raise classify_handoff_error(exc) from exc

    def get_last_session(
        self,
        *,
        user_id: str,
        agent_id: Optional[str],
        requester_agent_id: str,
        namespace: str,
        repo: Optional[str],
        statuses: Optional[List[str]] = None,
    ) -> Optional[Dict[str, Any]]:
        self._session_token(
            user_id=user_id,
            requester_agent_id=requester_agent_id,
            capabilities=["read_handoff"],
            namespace=namespace,
        )
        try:
            return self.client.get_last_session(
                user_id=user_id,
                agent_id=agent_id,
                requester_agent_id=requester_agent_id,
                repo=repo,
                statuses=statuses,
            )
        except Exception as exc:
            raise classify_handoff_error(exc) from exc

    def list_sessions(
        self,
        *,
        user_id: str,
        agent_id: Optional[str],
        requester_agent_id: str,
        namespace: str,
        repo: Optional[str],
        status: Optional[str],
        statuses: Optional[List[str]],
        limit: int,
    ) -> List[Dict[str, Any]]:
        self._session_token(
            user_id=user_id,
            requester_agent_id=requester_agent_id,
            capabilities=["read_handoff"],
            namespace=namespace,
        )
        try:
            payload = self.client.list_sessions(
                user_id=user_id,
                agent_id=agent_id,
                requester_agent_id=requester_agent_id,
                repo=repo,
                status=status,
                statuses=statuses,
                limit=limit,
            )
        except Exception as exc:
            raise classify_handoff_error(exc) from exc
        return list(payload.get("sessions", []))

    def auto_resume_context(
        self,
        *,
        user_id: str,
        agent_id: str,
        namespace: str,
        repo_path: str,
        branch: Optional[str],
        lane_type: str,
        objective: str,
        agent_role: Optional[str],
        statuses: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        self._session_token(
            user_id=user_id,
            requester_agent_id=agent_id,
            capabilities=["read_handoff"],
            namespace=namespace,
        )
        try:
            return self.client.handoff_resume(
                user_id=user_id,
                agent_id=agent_id,
                requester_agent_id=agent_id,
                repo_path=repo_path,
                branch=branch,
                lane_type=lane_type,
                objective=objective,
                agent_role=agent_role,
                namespace=namespace,
                statuses=statuses,
                auto_create=True,
            )
        except Exception as exc:
            raise classify_handoff_error(exc) from exc

    def auto_checkpoint(
        self,
        *,
        user_id: str,
        agent_id: str,
        namespace: str,
        repo_path: str,
        branch: Optional[str],
        lane_id: Optional[str],
        lane_type: str,
        objective: str,
        agent_role: Optional[str],
        confidentiality_scope: str,
        payload: Dict[str, Any],
        event_type: str,
    ) -> Dict[str, Any]:
        self._session_token(
            user_id=user_id,
            requester_agent_id=agent_id,
            capabilities=["write_handoff"],
            namespace=namespace,
        )
        checkpoint_payload = dict(payload)
        checkpoint_payload.update(
            {
                "user_id": user_id,
                "agent_id": agent_id,
                "requester_agent_id": agent_id,
                "repo_path": repo_path,
                "branch": branch,
                "lane_id": lane_id,
                "lane_type": lane_type,
                "objective": objective,
                "agent_role": agent_role,
                "namespace": namespace,
                "confidentiality_scope": confidentiality_scope,
                "event_type": event_type,
            }
        )
        try:
            return self.client.handoff_checkpoint(**checkpoint_payload)
        except Exception as exc:
            raise classify_handoff_error(exc) from exc


def create_handoff_backend(memory):
    """Create the configured handoff backend for MCP continuity paths."""
    api_url = os.environ.get("ENGRAM_API_URL")

    if api_url:
        return HostedHandoffBackend(api_url=api_url)
    return LocalHandoffBackend(memory)
