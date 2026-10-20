"""Request limits, input rules and metrics for the API.

The rate limiter keeps its buckets in the memory of one process. With more than one API replica,
each replica has its own buckets, thus the real limit is the limit multiplied by the replicas. A
reverse proxy or a shared store (for example Redis) must enforce a strict global limit.
"""

import re
import threading
import time
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass, field

TENANT_ID = re.compile(r"^[a-z0-9][a-z0-9-]{0,62}$")
"""Tenant IDs are lowercase words with hyphens. Any other value is not a tenant (HTTP 404)."""

SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Cross-Origin-Resource-Policy": "same-origin",
}
API_ONLY_HEADERS = {
    # JSON and text responses run no scripts. The /docs page is not under /v1.
    "Content-Security-Policy": "default-src 'none'; frame-ancestors 'none'",
    "Cache-Control": "no-store",
}


@dataclass
class _Bucket:
    tokens: float
    updated: float


@dataclass
class RateLimiter:
    """A token bucket for each key: ``per_minute`` requests, with bursts up to ``burst``."""

    per_minute: float
    burst: int
    clock: Callable[[], float] | None = None
    _buckets: dict[str, _Bucket] = field(default_factory=dict)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def _now(self) -> float:
        return (self.clock or time.monotonic)()

    def allow(self, key: str) -> tuple[bool, float]:
        """Take one token. Returns (allowed, seconds until the next token)."""
        rate = self.per_minute / 60.0
        now = self._now()
        with self._lock:
            b = self._buckets.get(key)
            if b is None:
                b = self._buckets[key] = _Bucket(tokens=float(self.burst), updated=now)
            b.tokens = min(float(self.burst), b.tokens + (now - b.updated) * rate)
            b.updated = now
            if b.tokens >= 1.0:
                b.tokens -= 1.0
                return True, 0.0
            return False, (1.0 - b.tokens) / rate if rate > 0 else 60.0


LATENCY_BUCKETS = (0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0)


@dataclass
class Metrics:
    """Request counters and a latency histogram in the Prometheus text format, with no library."""

    _requests: dict[tuple[str, str, int], int] = field(default_factory=lambda: defaultdict(int))
    _latency: dict[str, list[int]] = field(default_factory=dict)
    _latency_sum: dict[str, float] = field(default_factory=lambda: defaultdict(float))
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def observe(self, method: str, route: str, status: int, seconds: float) -> None:
        with self._lock:
            self._requests[(method, route, status)] += 1
            counts = self._latency.setdefault(route, [0] * (len(LATENCY_BUCKETS) + 1))
            for i, edge in enumerate(LATENCY_BUCKETS):
                if seconds <= edge:
                    counts[i] += 1
            counts[-1] += 1
            self._latency_sum[route] += seconds

    def render(self, gauges: dict[str, dict[str, float]] | None = None) -> str:
        lines = [
            "# HELP fdeops_http_requests_total HTTP requests by method, route and status.",
            "# TYPE fdeops_http_requests_total counter",
        ]
        with self._lock:
            for (m, r, s), n in sorted(self._requests.items()):
                lines.append(
                    f'fdeops_http_requests_total{{method="{m}",route="{r}",status="{s}"}} {n}'
                )
            lines += [
                "# HELP fdeops_http_request_seconds Request latency.",
                "# TYPE fdeops_http_request_seconds histogram",
            ]
            for route, counts in sorted(self._latency.items()):
                for edge, c in zip(LATENCY_BUCKETS, counts, strict=False):
                    lines.append(
                        f'fdeops_http_request_seconds_bucket{{route="{route}",le="{edge}"}} {c}'
                    )
                lines.append(
                    f'fdeops_http_request_seconds_bucket{{route="{route}",le="+Inf"}} {counts[-1]}'
                )
                lines.append(
                    f'fdeops_http_request_seconds_sum{{route="{route}"}} '
                    f"{self._latency_sum[route]:.6f}"
                )
                lines.append(f'fdeops_http_request_seconds_count{{route="{route}"}} {counts[-1]}')
        for name, series in (gauges or {}).items():
            lines.append(f"# TYPE {name} gauge")
            for label, value in sorted(series.items()):
                lines.append(f'{name}{{status="{label}"}} {value:g}')
        return "\n".join(lines) + "\n"
