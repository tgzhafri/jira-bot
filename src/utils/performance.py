"""
Performance monitoring utilities for API operations.

Provides timing, counting, and logging for API calls to enable
observability and performance regression detection.
"""

import logging
import time
import threading
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class APICallMetric:
    """Single API call measurement."""

    endpoint: str
    method: str
    duration_ms: float
    cached: bool = False
    status_code: Optional[int] = None


@dataclass
class PerformanceStats:
    """Aggregated performance statistics for a job run."""

    total_api_calls: int = 0
    total_cache_hits: int = 0
    total_duration_ms: float = 0.0
    calls_by_endpoint: Dict[str, int] = field(default_factory=dict)
    slowest_calls: List[APICallMetric] = field(default_factory=list)

    def record_call(self, metric: APICallMetric) -> None:
        """Record a single API call metric."""
        self.total_api_calls += 1
        self.total_duration_ms += metric.duration_ms
        if metric.cached:
            self.total_cache_hits += 1

        # Track by endpoint prefix (first path segment)
        endpoint_key = metric.endpoint.split("?")[0].split("/")[0]
        self.calls_by_endpoint[endpoint_key] = (
            self.calls_by_endpoint.get(endpoint_key, 0) + 1
        )

        # Keep top 5 slowest calls
        self.slowest_calls.append(metric)
        self.slowest_calls.sort(key=lambda m: m.duration_ms, reverse=True)
        self.slowest_calls = self.slowest_calls[:5]

    def log_summary(self, job_name: str = "Job") -> None:
        """Log a summary of performance stats."""
        logger.info(
            "📊 %s Performance Summary: "
            "%d API calls (%d cached), %.1fs total API time",
            job_name,
            self.total_api_calls,
            self.total_cache_hits,
            self.total_duration_ms / 1000,
        )
        if self.calls_by_endpoint:
            breakdown = ", ".join(
                f"{k}={v}" for k, v in sorted(
                    self.calls_by_endpoint.items(),
                    key=lambda x: x[1],
                    reverse=True,
                )[:5]
            )
            logger.info("   Calls by endpoint: %s", breakdown)
        if self.slowest_calls:
            slowest = self.slowest_calls[0]
            logger.info(
                "   Slowest call: %s %s (%.0fms)",
                slowest.method,
                slowest.endpoint[:80],
                slowest.duration_ms,
            )


class PerformanceTracker:
    """Thread-safe performance tracker for a single job run.

    Usage:
        tracker = PerformanceTracker()
        with tracker.track_call("search/jql", "GET") as metric:
            response = session.get(...)
            metric.status_code = response.status_code
        tracker.stats.log_summary("Report Generation")
    """

    def __init__(self):
        self.stats = PerformanceStats()
        self._lock = threading.Lock()

    @contextmanager
    def track_call(self, endpoint: str, method: str = "GET", cached: bool = False):
        """Context manager to time an API call.

        Args:
            endpoint: The API endpoint being called.
            method: HTTP method.
            cached: Whether this was served from cache.

        Yields:
            APICallMetric that can be updated with status_code.
        """
        metric = APICallMetric(
            endpoint=endpoint,
            method=method,
            duration_ms=0.0,
            cached=cached,
        )

        start = time.perf_counter()
        try:
            yield metric
        finally:
            metric.duration_ms = (time.perf_counter() - start) * 1000
            with self._lock:
                self.stats.record_call(metric)

    def record_cached_call(self, endpoint: str, method: str = "GET") -> None:
        """Record a cache hit (no timing needed)."""
        metric = APICallMetric(
            endpoint=endpoint,
            method=method,
            duration_ms=0.0,
            cached=True,
        )
        with self._lock:
            self.stats.record_call(metric)


@contextmanager
def timed_operation(operation_name: str):
    """Context manager that logs the duration of an operation.

    Args:
        operation_name: Human-readable name for the operation.

    Usage:
        with timed_operation("Fetch all worklogs"):
            ...
    """
    start = time.perf_counter()
    logger.info("⏱️  Starting: %s", operation_name)
    try:
        yield
    finally:
        elapsed = time.perf_counter() - start
        logger.info("⏱️  Completed: %s in %.1fs", operation_name, elapsed)
