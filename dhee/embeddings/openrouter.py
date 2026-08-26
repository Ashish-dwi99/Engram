"""OpenRouter embeddings.

OpenRouter is the one model API the host already routes everything through, so keeping
embeddings on it means one key, one bill and one place where rate limits show up —
rather than a second provider account that exists only for retrieval.

Two things about it are not obvious and cost an afternoon each to discover:

- **The public ``/models`` listing does not include embedding or reranking models.** It
  returns chat models only. The models are real and free, but you have to ask
  ``/models/{id}/endpoints`` for them, which is why they look absent.
- **``dimensions`` must not be sent.** The OpenAI-compatible surface accepts the
  parameter on paper; the NVIDIA-backed models reject or ignore it, and the vector
  width is fixed by the model (2048 for ``llama-nemotron-embed-vl-1b-v2``). The width
  is therefore something to *record*, not to request.

Measured on the free tier: batches of 128 return in ~1.6s, and 40 back-to-back requests
covering 5,120 chunks completed with no 429 at all. The limit that does exist is a
daily request cap on ``:free`` models, so the batch size matters much more than the
rate — hence 128 per call rather than a stream of singles.
"""

from __future__ import annotations

import logging
import os
import time
from typing import Any, Dict, List, Optional

from dhee.embeddings.base import BaseEmbedder

logger = logging.getLogger(__name__)

DEFAULT_BASE_URL = "https://openrouter.ai/api/v1"
DEFAULT_MODEL = "nvidia/llama-nemotron-embed-vl-1b-v2:free"
DEFAULT_DIMS = 2048
DEFAULT_BATCH_SIZE = 128
_MAX_RETRIES = 4
_BACKOFF_BASE_SECONDS = 1.5

# Retrieval quality depends on the document and the query being embedded for their
# different roles; asymmetric models lose real accuracy when both sides look the same.
INPUT_TYPE_DOCUMENT = "passage"
INPUT_TYPE_QUERY = "query"


class OpenRouterEmbedder(BaseEmbedder):
    """Embeddings over OpenRouter's OpenAI-compatible ``/embeddings`` route."""

    def __init__(self, config: Optional[dict] = None):
        super().__init__(config)
        try:
            import requests  # noqa: F401
        except Exception as exc:  # pragma: no cover - requests is a hard dependency
            raise ImportError("requests is required for OpenRouterEmbedder") from exc

        api_key = (
            self.config.get("api_key")
            or os.getenv("OPENROUTER_API_KEY")
            or os.getenv("DHEE_OPENROUTER_API_KEY")
        )
        if not api_key:
            raise ValueError(
                "OpenRouter API key required. Set config['api_key'] or OPENROUTER_API_KEY."
            )
        self.api_key = api_key
        self.base_url = str(self.config.get("base_url") or DEFAULT_BASE_URL).rstrip("/")
        self.model = self.config.get("model") or DEFAULT_MODEL
        self.dims = int(self.config.get("embedding_dims") or DEFAULT_DIMS)
        self.batch_size = max(1, int(self.config.get("batch_size") or DEFAULT_BATCH_SIZE))
        self.timeout = int(self.config.get("timeout") or 90)
        self.default_input_type = self.config.get("input_type") or INPUT_TYPE_DOCUMENT

    # ------------------------------------------------------------------ api

    def embed(self, text: str, memory_action: Optional[str] = None) -> List[float]:
        vectors = self.embed_batch([text], memory_action=memory_action)
        return vectors[0] if vectors else [0.0] * self.dims

    def embed_batch(
        self,
        texts: List[str],
        memory_action: Optional[str] = None,
        *,
        input_type: Optional[str] = None,
    ) -> List[List[float]]:
        if not texts:
            return []
        resolved_type = input_type or self.default_input_type
        vectors: List[List[float]] = []
        for start in range(0, len(texts), self.batch_size):
            window = texts[start : start + self.batch_size]
            vectors.extend(self._embed_window(window, resolved_type))
        return vectors

    def embed_query(self, text: str) -> List[float]:
        """Embed the query side of the asymmetry."""
        vectors = self.embed_batch([text], input_type=INPUT_TYPE_QUERY)
        return vectors[0] if vectors else [0.0] * self.dims

    # -------------------------------------------------------------- internal

    def _embed_window(self, texts: List[str], input_type: str) -> List[List[float]]:
        import requests

        payload: Dict[str, Any] = {"model": self.model, "input": texts}
        if input_type:
            payload["input_type"] = input_type
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        last_error: Optional[Exception] = None
        for attempt in range(_MAX_RETRIES):
            try:
                response = requests.post(
                    f"{self.base_url}/embeddings", json=payload, headers=headers, timeout=self.timeout
                )
                if response.status_code in {429, 500, 502, 503, 504}:
                    # The free tier showed no 429 under load, but a free tier can be
                    # re-priced without notice, so treat throttling as expected rather
                    # than exceptional and let the caller's progress survive it.
                    delay = self._retry_delay(response, attempt)
                    logger.warning(
                        "OpenRouter embeddings %s; retrying in %.1fs (attempt %d/%d)",
                        response.status_code, delay, attempt + 1, _MAX_RETRIES,
                    )
                    time.sleep(delay)
                    continue
                response.raise_for_status()
                return self._vectors_from(response.json(), expected=len(texts))
            except Exception as exc:  # noqa: BLE001 - retried, then re-raised below
                last_error = exc
                if attempt == _MAX_RETRIES - 1:
                    break
                time.sleep(_BACKOFF_BASE_SECONDS * (2**attempt))

        raise RuntimeError(
            f"OpenRouter embedding failed after {_MAX_RETRIES} attempts (model={self.model}): {last_error}"
        )

    @staticmethod
    def _retry_delay(response: Any, attempt: int) -> float:
        header = response.headers.get("Retry-After") if hasattr(response, "headers") else None
        if header:
            try:
                return min(60.0, float(header))
            except (TypeError, ValueError):
                pass
        return _BACKOFF_BASE_SECONDS * (2**attempt)

    def _vectors_from(self, body: Dict[str, Any], *, expected: int) -> List[List[float]]:
        rows = body.get("data")
        if not isinstance(rows, list) or len(rows) != expected:
            raise RuntimeError(
                f"OpenRouter returned {len(rows) if isinstance(rows, list) else 'no'} "
                f"embeddings for {expected} inputs"
            )
        # Order is documented but cheap to guarantee; a silently mis-ordered batch
        # attaches every vector to the wrong chunk and is near-impossible to spot later.
        ordered = sorted(rows, key=lambda row: int(row.get("index", 0)))
        vectors = [list(row["embedding"]) for row in ordered]
        width = len(vectors[0]) if vectors else self.dims
        if width != self.dims:
            logger.info("OpenRouter model %s returned %d dims; recording that width", self.model, width)
            self.dims = width
        return vectors
