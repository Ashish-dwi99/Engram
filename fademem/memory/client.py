from typing import Any, Dict, List, Optional


class MemoryClient:
    """Thin HTTP client mirroring mem0's MemoryClient interface."""

    def __init__(
        self,
        api_key: str = None,
        host: str = "https://api.fadem.ai",
        org_id: str = None,
        project_id: str = None,
    ):
        try:
            import requests  # noqa: F401
        except Exception as exc:
            raise ImportError("requests package is required for MemoryClient") from exc

        self.api_key = api_key
        self.host = host.rstrip("/")
        self.org_id = org_id
        self.project_id = project_id

    def _headers(self) -> Dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        if self.org_id:
            headers["X-Org-Id"] = self.org_id
        if self.project_id:
            headers["X-Project-Id"] = self.project_id
        return headers

    def _request(self, method: str, path: str, *, params: Dict[str, Any] = None, json_body: Dict[str, Any] = None):
        import requests

        url = f"{self.host}{path}"
        response = requests.request(method, url, headers=self._headers(), params=params, json=json_body, timeout=60)
        response.raise_for_status()
        return response.json()

    def add(self, messages, **kwargs) -> Dict[str, Any]:
        payload = {"messages": messages}
        payload.update(kwargs)
        return self._request("POST", "/v1/memories/", json_body=payload)

    def search(self, query: str, **kwargs) -> Dict[str, Any]:
        payload = {"query": query}
        payload.update(kwargs)
        return self._request("POST", "/v1/memories/search/", json_body=payload)

    def get(self, memory_id: str, **kwargs) -> Dict[str, Any]:
        return self._request("GET", f"/v1/memories/{memory_id}/", params=kwargs)

    def get_all(self, **kwargs) -> Dict[str, Any]:
        return self._request("GET", "/v1/memories/", params=kwargs)

    def update(self, memory_id: str, data: str = None, metadata: Dict[str, Any] = None, **kwargs) -> Dict[str, Any]:
        payload: Dict[str, Any] = {}
        if data is not None:
            payload["data"] = data
        if metadata is not None:
            payload["metadata"] = metadata
        payload.update(kwargs)
        return self._request("PUT", f"/v1/memories/{memory_id}/", json_body=payload)

    def delete(self, memory_id: str, **kwargs) -> Dict[str, Any]:
        return self._request("DELETE", f"/v1/memories/{memory_id}/", params=kwargs)

    def delete_all(self, **kwargs) -> Dict[str, Any]:
        return self._request("DELETE", "/v1/memories/", params=kwargs)

    def history(self, memory_id: str, **kwargs) -> List[Dict[str, Any]]:
        return self._request("GET", f"/v1/memories/{memory_id}/history/", params=kwargs)
