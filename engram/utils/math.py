"""Shared math utilities for engram."""

from typing import List

try:
    import numpy as np

    def cosine_similarity(a: List[float], b: List[float]) -> float:
        """Compute cosine similarity between two vectors using NumPy."""
        if not a or not b or len(a) != len(b):
            return 0.0
        arr_a = np.asarray(a, dtype=np.float64)
        arr_b = np.asarray(b, dtype=np.float64)
        dot = np.dot(arr_a, arr_b)
        denom = np.sqrt(np.dot(arr_a, arr_a) * np.dot(arr_b, arr_b))
        return float(dot / denom) if denom else 0.0

except ImportError:

    def cosine_similarity(a: List[float], b: List[float]) -> float:  # type: ignore[misc]
        """Compute cosine similarity between two vectors (pure-Python fallback)."""
        if not a or not b or len(a) != len(b):
            return 0.0
        dot = sum(x * y for x, y in zip(a, b))
        norm_a = sum(x * x for x in a) ** 0.5
        norm_b = sum(x * x for x in b) ** 0.5
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return dot / (norm_a * norm_b)
