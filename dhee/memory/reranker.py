"""Neural reranker for second-stage retrieval refinement.

Uses a cross-encoder model to re-score (query, passage) pairs with full
attention, producing much more accurate relevance scores than embedding
cosine similarity alone.
"""

import logging
import os
import time
from typing import Any, Dict, List, Optional

import requests

logger = logging.getLogger(__name__)


class NvidiaReranker:
    """NVIDIA NIM reranker using the /reranking endpoint."""

    _DEFAULT_URL = (
        "https://ai.api.nvidia.com/v1/retrieval/"
        "nvidia/llama-nemotron-rerank-vl-1b-v2/reranking"
    )

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        config = config or {}
        self.model = config.get("model", "nvidia/llama-nemotron-rerank-vl-1b-v2")
        api_key_env = config.get("api_key_env", "NVIDIA_API_KEY")
        self.api_key = config.get("api_key") or os.getenv(api_key_env)
        if not self.api_key:
            raise ValueError(
                f"NVIDIA API key required for reranker. Set config['api_key'] or {api_key_env} env var."
            )
        # Build URL from model name: dots become underscores for legacy
        # llama-3.2 model endpoints; slashes remain path separators.
        # e.g. nvidia/llama-3.2-nv-rerankqa-1b-v2 -> nvidia/llama-3_2-nv-rerankqa-1b-v2
        model_path = self.model.replace(".", "_")
        self.url = config.get(
            "url",
            f"https://ai.api.nvidia.com/v1/retrieval/{model_path}/reranking",
        )
        self.timeout = config.get("timeout", 30)
        self.max_retries = config.get("max_retries", 2)
        self.strict_schema = bool(config.get("strict_schema", True))

    def rerank(
        self,
        query: str,
        passages: List[str],
        top_n: int = 0,
    ) -> List[Dict[str, Any]]:
        """Rerank passages against a query.

        Args:
            query: The search query.
            passages: List of passage texts to rerank.
            top_n: Number of top results to return (0 = return all, re-sorted).

        Returns:
            List of dicts with keys: index (original position), logit, text.
            Sorted by logit descending.
        """
        if not passages:
            return []
        if len(passages) == 1:
            return [{"index": 0, "logit": 0.0, "text": passages[0]}]

        payload = {
            "model": self.model,
            "query": {"text": query},
            "passages": [{"text": p} for p in passages],
        }
        if top_n > 0:
            payload["top_n"] = top_n

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

        last_exc = None
        for attempt in range(self.max_retries + 1):
            try:
                t0 = time.monotonic()
                resp = requests.post(
                    self.url,
                    json=payload,
                    headers=headers,
                    timeout=self.timeout,
                )
                elapsed_ms = (time.monotonic() - t0) * 1000
                resp.raise_for_status()
                data = resp.json()

                rankings = data.get("rankings")
                if rankings is None and isinstance(data.get("data"), dict):
                    rankings = data["data"].get("rankings")
                if not isinstance(rankings, list) or not rankings:
                    msg = "Reranker response missing non-empty rankings list"
                    if self.strict_schema:
                        raise ValueError(msg)
                    logger.warning(msg)
                    return []

                results = []
                for r in rankings:
                    if not isinstance(r, dict):
                        if self.strict_schema:
                            raise ValueError(f"Invalid ranking row type: {type(r)}")
                        logger.warning("Skipping invalid ranking row type: %s", type(r))
                        continue

                    idx = r.get("index")
                    try:
                        idx = int(idx)
                    except (TypeError, ValueError):
                        if self.strict_schema:
                            raise ValueError(f"Invalid ranking index: {idx!r}")
                        logger.warning("Skipping ranking row with invalid index: %r", idx)
                        continue
                    if idx < 0 or idx >= len(passages):
                        if self.strict_schema:
                            raise ValueError(f"Ranking index out of range: {idx}")
                        logger.warning("Skipping ranking row with out-of-range index: %s", idx)
                        continue

                    score = r.get("logit")
                    if score is None:
                        score = r.get("score")
                    if score is None:
                        score = r.get("relevance_score")
                    if score is None:
                        if self.strict_schema:
                            raise ValueError("Ranking row missing logit/score/relevance_score")
                        logger.warning("Skipping ranking row without usable score field")
                        continue
                    try:
                        score = float(score)
                    except (TypeError, ValueError):
                        if self.strict_schema:
                            raise ValueError(f"Invalid score value for index {idx}: {score!r}")
                        logger.warning("Skipping ranking row with invalid score: %r", score)
                        continue

                    results.append({
                        "index": idx,
                        "logit": score,
                        "text": passages[idx] if idx < len(passages) else "",
                    })
                if not results:
                    msg = "Reranker response produced no valid ranking rows"
                    if self.strict_schema:
                        raise ValueError(msg)
                    logger.warning(msg)
                    return []
                results.sort(key=lambda x: x["logit"], reverse=True)
                logger.debug(
                    "Reranked %d passages in %.0fms (top logit=%.2f)",
                    len(passages), elapsed_ms,
                    results[0]["logit"] if results else 0.0,
                )
                return results

            except Exception as exc:
                last_exc = exc
                if attempt < self.max_retries:
                    delay = min(2 ** attempt, 4)
                    logger.warning(
                        "Reranker retry %d/%d after %ss: %s",
                        attempt + 1, self.max_retries, delay, exc,
                    )
                    time.sleep(delay)
                else:
                    logger.error("Reranker failed after %d attempts: %s", self.max_retries + 1, exc)

        raise RuntimeError(f"Reranker failed: {last_exc}") from last_exc


class Qwen3Reranker:
    """Local Qwen3-Reranker-0.6B via sentence-transformers cross-encoder.

    0.6B params, MTEB-R 65.80 (vs BGE 57.03). CPU-native, zero API cost.
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        config = config or {}
        self.model_name = config.get("model", "Qwen/Qwen3-Reranker-0.6B")
        self.device = config.get("device", "cpu")
        self._model = None

    def _ensure_model(self):
        if self._model is not None:
            return
        try:
            from sentence_transformers import CrossEncoder
        except ImportError:
            raise ImportError(
                "sentence-transformers is required for Qwen3Reranker. "
                "Install with: pip install sentence-transformers"
            )
        logger.info("Loading Qwen3 reranker: %s", self.model_name)
        self._model = CrossEncoder(self.model_name, device=self.device)
        logger.info("Qwen3 reranker loaded")

    def rerank(
        self,
        query: str,
        passages: List[str],
        top_n: int = 0,
    ) -> List[Dict[str, Any]]:
        """Rerank passages using local cross-encoder model."""
        if not passages:
            return []
        if len(passages) == 1:
            return [{"index": 0, "logit": 0.0, "text": passages[0]}]

        self._ensure_model()

        pairs = [(query, p) for p in passages]
        t0 = time.monotonic()
        scores = self._model.predict(pairs, show_progress_bar=False)
        elapsed_ms = (time.monotonic() - t0) * 1000

        results = [
            {"index": i, "logit": float(score), "text": passages[i]}
            for i, score in enumerate(scores)
        ]
        results.sort(key=lambda x: x["logit"], reverse=True)

        if top_n > 0:
            results = results[:top_n]

        logger.debug(
            "Qwen3 reranked %d passages in %.0fms (top logit=%.2f)",
            len(passages), elapsed_ms,
            results[0]["logit"] if results else 0.0,
        )
        return results


class OpenRouterReranker:
    """Cross-encoder reranking over OpenRouter's ``/rerank`` route.

    Same model as :class:`NvidiaReranker` reaches through NIM, but on the key the host
    already has. Two differences from the NIM surface worth knowing: the route is
    ``/rerank`` (``/reranking`` is a 404 here), and the request field is ``documents``
    of plain strings rather than ``passages`` of objects. Scores come back as
    ``relevance_score``, higher being more relevant.
    """

    _DEFAULT_BASE_URL = "https://openrouter.ai/api/v1"
    _DEFAULT_MODEL = "nvidia/llama-nemotron-rerank-vl-1b-v2:free"

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        config = config or {}
        self.model = config.get("model", self._DEFAULT_MODEL)
        api_key_env = config.get("api_key_env", "OPENROUTER_API_KEY")
        self.api_key = config.get("api_key") or os.getenv(api_key_env)
        if not self.api_key:
            raise ValueError(
                f"OpenRouter API key required for reranker. Set config['api_key'] or {api_key_env}."
            )
        base_url = str(config.get("base_url") or self._DEFAULT_BASE_URL).rstrip("/")
        self.url = config.get("url", f"{base_url}/rerank")
        self.timeout = config.get("timeout", 30)
        self.max_retries = config.get("max_retries", 2)

    def rerank(self, query: str, passages: List[str], top_n: int = 0) -> List[Dict[str, Any]]:
        if not passages:
            return []
        if len(passages) == 1:
            return [{"index": 0, "logit": 0.0, "text": passages[0]}]

        payload: Dict[str, Any] = {"model": self.model, "query": query, "documents": passages}
        if top_n > 0:
            payload["top_n"] = top_n
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}

        last_exc: Optional[Exception] = None
        for attempt in range(self.max_retries + 1):
            try:
                resp = requests.post(self.url, json=payload, headers=headers, timeout=self.timeout)
                resp.raise_for_status()
                rows = resp.json().get("results") or []
                results = []
                for row in rows:
                    try:
                        index = int(row["index"])
                    except (KeyError, TypeError, ValueError):
                        continue
                    if not 0 <= index < len(passages):
                        continue
                    score = row.get("relevance_score", row.get("score", row.get("logit")))
                    if score is None:
                        continue
                    results.append({"index": index, "logit": float(score), "text": passages[index]})
                results.sort(key=lambda item: item["logit"], reverse=True)
                return results[:top_n] if top_n > 0 else results
            except Exception as exc:  # noqa: BLE001 - retried, then reported below
                last_exc = exc
                if attempt < self.max_retries:
                    time.sleep(1.5 * (2**attempt))

        # Reranking is a refinement, not a gate. Losing it should cost ordering
        # quality, never the answer itself, so the caller sees an empty list and
        # falls back to vector order.
        logger.warning("OpenRouter rerank failed (model=%s): %s", self.model, last_exc)
        return []


def create_reranker(config: Optional[Dict[str, Any]] = None):
    """Factory: create a reranker from config, or return None if disabled."""
    if not config:
        return None
    provider = config.get("provider", "nvidia")
    if provider == "nvidia":
        return NvidiaReranker(config)
    if provider == "qwen":
        return Qwen3Reranker(config)
    if provider == "openrouter":
        return OpenRouterReranker(config)
    logger.warning("Unknown reranker provider: %s", provider)
    return None
