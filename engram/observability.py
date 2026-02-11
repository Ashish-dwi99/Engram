"""Engram Observability Module.

Provides structured logging, metrics collection, and monitoring capabilities.

Usage:
    from engram.observability import metrics, logger

    # Log operations
    logger.info("Memory added", memory_id="abc123", user_id="u1")

    # Record metrics
    metrics.record_add(latency_ms=45, user_id="u1")
    metrics.record_search(latency_ms=120, results_count=5)

    # Get stats
    print(metrics.get_summary())
"""

from __future__ import annotations

import json
import logging
import time
from collections import defaultdict
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Callable
import threading


# ============================================================================
# Structured Logger
# ============================================================================

class StructuredLogger:
    """JSON-structured logger for Engram operations."""

    def __init__(self, name: str = "engram", level: int = logging.INFO):
        self._logger = logging.getLogger(name)
        self._logger.setLevel(level)
        self._context: Dict[str, Any] = {}

        # Add JSON handler if not already configured
        if not self._logger.handlers:
            handler = logging.StreamHandler()
            handler.setFormatter(StructuredFormatter())
            self._logger.addHandler(handler)

    def with_context(self, **kwargs) -> "StructuredLogger":
        """Create a new logger with additional context."""
        new_logger = StructuredLogger.__new__(StructuredLogger)
        new_logger._logger = self._logger
        new_logger._context = {**self._context, **kwargs}
        return new_logger

    def _log(self, level: int, message: str, **kwargs):
        """Log with structured data."""
        extra = {
            "structured_data": {
                **self._context,
                **kwargs,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        }
        self._logger.log(level, message, extra=extra)

    def debug(self, message: str, **kwargs):
        self._log(logging.DEBUG, message, **kwargs)

    def info(self, message: str, **kwargs):
        self._log(logging.INFO, message, **kwargs)

    def warning(self, message: str, **kwargs):
        self._log(logging.WARNING, message, **kwargs)

    def error(self, message: str, **kwargs):
        self._log(logging.ERROR, message, **kwargs)

    def critical(self, message: str, **kwargs):
        self._log(logging.CRITICAL, message, **kwargs)


class StructuredFormatter(logging.Formatter):
    """Format log records as JSON."""

    def format(self, record: logging.LogRecord) -> str:
        log_data = {
            "level": record.levelname,
            "message": record.getMessage(),
            "logger": record.name,
        }

        # Add structured data if present
        if hasattr(record, "structured_data"):
            log_data.update(record.structured_data)

        # Add exception info if present
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_data)


# ============================================================================
# Metrics Collector
# ============================================================================

@dataclass
class OperationMetrics:
    """Metrics for a single operation type."""
    count: int = 0
    total_latency_ms: float = 0.0
    min_latency_ms: float = float("inf")
    max_latency_ms: float = 0.0
    errors: int = 0
    last_operation: Optional[str] = None

    def record(self, latency_ms: float, error: bool = False):
        self.count += 1
        self.total_latency_ms += latency_ms
        self.min_latency_ms = min(self.min_latency_ms, latency_ms)
        self.max_latency_ms = max(self.max_latency_ms, latency_ms)
        if error:
            self.errors += 1
        self.last_operation = datetime.now(timezone.utc).isoformat()

    @property
    def avg_latency_ms(self) -> float:
        return self.total_latency_ms / self.count if self.count > 0 else 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "count": self.count,
            "avg_latency_ms": round(self.avg_latency_ms, 2),
            "min_latency_ms": round(self.min_latency_ms, 2) if self.count > 0 else 0,
            "max_latency_ms": round(self.max_latency_ms, 2),
            "errors": self.errors,
            "error_rate": round(self.errors / self.count, 4) if self.count > 0 else 0,
            "last_operation": self.last_operation,
        }


@dataclass
class MemoryMetrics:
    """Memory-specific metrics."""
    total_added: int = 0
    total_searched: int = 0
    total_decayed: int = 0
    total_forgotten: int = 0
    total_promoted: int = 0
    search_results_total: int = 0
    total_masked_hits: int = 0
    total_staged_commits: int = 0
    total_auto_stashed: int = 0
    total_commit_approved: int = 0
    total_commit_rejected: int = 0
    total_ref_protected_skips: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_added": self.total_added,
            "total_searched": self.total_searched,
            "total_decayed": self.total_decayed,
            "total_forgotten": self.total_forgotten,
            "total_promoted": self.total_promoted,
            "total_masked_hits": self.total_masked_hits,
            "total_staged_commits": self.total_staged_commits,
            "total_auto_stashed": self.total_auto_stashed,
            "total_commit_approved": self.total_commit_approved,
            "total_commit_rejected": self.total_commit_rejected,
            "total_ref_protected_skips": self.total_ref_protected_skips,
            "avg_search_results": round(
                self.search_results_total / self.total_searched, 2
            ) if self.total_searched > 0 else 0,
        }


class MetricsCollector:
    """Collects and exposes Engram metrics."""

    def __init__(self):
        self._lock = threading.Lock()
        self._operations: Dict[str, OperationMetrics] = defaultdict(OperationMetrics)
        self._memory = MemoryMetrics()
        self._start_time = datetime.now(timezone.utc)
        self._custom_gauges: Dict[str, float] = {}

    def record_operation(
        self,
        operation: str,
        latency_ms: float,
        error: bool = False,
        **tags
    ):
        """Record an operation metric."""
        with self._lock:
            self._operations[operation].record(latency_ms, error)

    def record_add(self, latency_ms: float, count: int = 1, **tags):
        """Record memory add operation."""
        self.record_operation("add", latency_ms, **tags)
        with self._lock:
            self._memory.total_added += count

    def record_search(self, latency_ms: float, results_count: int = 0, **tags):
        """Record memory search operation."""
        self.record_operation("search", latency_ms, **tags)
        with self._lock:
            self._memory.total_searched += 1
            self._memory.search_results_total += results_count

    def record_decay(
        self,
        latency_ms: float,
        decayed: int = 0,
        forgotten: int = 0,
        promoted: int = 0,
        **tags
    ):
        """Record decay operation."""
        self.record_operation("decay", latency_ms, **tags)
        with self._lock:
            self._memory.total_decayed += decayed
            self._memory.total_forgotten += forgotten
            self._memory.total_promoted += promoted

    def record_get(self, latency_ms: float, **tags):
        """Record memory get operation."""
        self.record_operation("get", latency_ms, **tags)

    def record_delete(self, latency_ms: float, **tags):
        """Record memory delete operation."""
        self.record_operation("delete", latency_ms, **tags)

    def record_masked_hits(self, count: int = 1):
        with self._lock:
            self._memory.total_masked_hits += max(0, int(count))

    def record_staged_commit(self, status: str):
        status_upper = (status or "").upper()
        with self._lock:
            self._memory.total_staged_commits += 1
            if status_upper == "AUTO_STASHED":
                self._memory.total_auto_stashed += 1

    def record_commit_approval(self, latency_ms: float):
        self.record_operation("commit_approve", latency_ms)
        with self._lock:
            self._memory.total_commit_approved += 1

    def record_commit_rejection(self):
        self.record_operation("commit_reject", 0)
        with self._lock:
            self._memory.total_commit_rejected += 1

    def record_ref_protected_skip(self, count: int = 1):
        with self._lock:
            self._memory.total_ref_protected_skips += max(0, int(count))

    def set_gauge(self, name: str, value: float):
        """Set a custom gauge metric."""
        with self._lock:
            self._custom_gauges[name] = value

    def get_summary(self) -> Dict[str, Any]:
        """Get a summary of all metrics."""
        with self._lock:
            uptime = (datetime.now(timezone.utc) - self._start_time).total_seconds()
            return {
                "uptime_seconds": round(uptime, 2),
                "operations": {
                    op: metrics.to_dict()
                    for op, metrics in self._operations.items()
                },
                "memory": self._memory.to_dict(),
                "gauges": dict(self._custom_gauges),
            }

    def get_prometheus_metrics(self) -> str:
        """Export metrics in Prometheus format."""
        lines = []
        summary = self.get_summary()

        # Operation metrics
        for op, data in summary["operations"].items():
            lines.append(f'engram_operation_count{{operation="{op}"}} {data["count"]}')
            lines.append(f'engram_operation_latency_avg_ms{{operation="{op}"}} {data["avg_latency_ms"]}')
            lines.append(f'engram_operation_errors{{operation="{op}"}} {data["errors"]}')

        # Memory metrics
        mem = summary["memory"]
        lines.append(f'engram_memories_added_total {mem["total_added"]}')
        lines.append(f'engram_memories_searched_total {mem["total_searched"]}')
        lines.append(f'engram_memories_decayed_total {mem["total_decayed"]}')
        lines.append(f'engram_memories_forgotten_total {mem["total_forgotten"]}')
        lines.append(f'engram_memories_promoted_total {mem["total_promoted"]}')
        lines.append(f'engram_memories_masked_hits_total {mem["total_masked_hits"]}')
        lines.append(f'engram_staged_commits_total {mem["total_staged_commits"]}')
        lines.append(f'engram_staged_auto_stashed_total {mem["total_auto_stashed"]}')
        lines.append(f'engram_commit_approved_total {mem["total_commit_approved"]}')
        lines.append(f'engram_commit_rejected_total {mem["total_commit_rejected"]}')
        lines.append(f'engram_ref_protected_skips_total {mem["total_ref_protected_skips"]}')

        # Custom gauges
        for name, value in summary["gauges"].items():
            safe_name = name.replace(".", "_").replace("-", "_")
            lines.append(f'engram_{safe_name} {value}')

        # Uptime
        lines.append(f'engram_uptime_seconds {summary["uptime_seconds"]}')

        return "\n".join(lines)

    @contextmanager
    def measure(self, operation: str, **tags):
        """Context manager to measure operation latency.

        Usage:
            with metrics.measure("search", user_id="u1"):
                results = memory.search(...)
        """
        start = time.perf_counter()
        error = False
        try:
            yield
        except Exception:
            error = True
            raise
        finally:
            latency_ms = (time.perf_counter() - start) * 1000
            self.record_operation(operation, latency_ms, error=error, **tags)


# ============================================================================
# Global Instances
# ============================================================================

# Global logger instance
logger = StructuredLogger("engram")

# Global metrics collector
metrics = MetricsCollector()


# ============================================================================
# Instrumentation Helpers
# ============================================================================

def instrument(operation: str):
    """Decorator to instrument a function with metrics.

    Usage:
        @instrument("search")
        def search(self, query, ...):
            ...
    """
    def decorator(func: Callable) -> Callable:
        def wrapper(*args, **kwargs):
            with metrics.measure(operation):
                return func(*args, **kwargs)
        wrapper.__name__ = func.__name__
        wrapper.__doc__ = func.__doc__
        return wrapper
    return decorator


# ============================================================================
# API Endpoints (for FastAPI integration)
# ============================================================================

def add_metrics_routes(app):
    """Add metrics endpoints to a FastAPI app.

    Usage:
        from engram.observability import add_metrics_routes
        add_metrics_routes(app)
    """
    from fastapi import Response

    @app.get("/metrics")
    async def prometheus_metrics():
        """Prometheus-compatible metrics endpoint."""
        return Response(
            content=metrics.get_prometheus_metrics(),
            media_type="text/plain"
        )

    @app.get("/metrics/json")
    async def json_metrics():
        """JSON metrics endpoint."""
        return metrics.get_summary()
