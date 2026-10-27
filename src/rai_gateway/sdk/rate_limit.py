"""In-process rate limiting for public SDK surfaces.

Fail-closed for enforcement paths: when limited, return RATE_LIMITED (deny),
never fail-open to ALLOW.
"""

from __future__ import annotations

import threading
import time
from collections import defaultdict, deque
from dataclasses import dataclass


@dataclass
class RateLimitResult:
    allowed: bool
    limit: int
    remaining: int
    reset_at: float


class SlidingWindowRateLimiter:
    """Simple process-local sliding window limiter."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    def check(
        self,
        key: str,
        *,
        limit: int,
        window_seconds: float,
    ) -> RateLimitResult:
        now = time.time()
        cutoff = now - window_seconds
        with self._lock:
            bucket = self._hits[key]
            while bucket and bucket[0] < cutoff:
                bucket.popleft()
            if len(bucket) >= limit:
                reset_at = (
                    bucket[0] + window_seconds if bucket else now + window_seconds
                )
                return RateLimitResult(
                    allowed=False,
                    limit=limit,
                    remaining=0,
                    reset_at=reset_at,
                )
            bucket.append(now)
            return RateLimitResult(
                allowed=True,
                limit=limit,
                remaining=max(0, limit - len(bucket)),
                reset_at=now + window_seconds,
            )


# Module singleton suitable for single-process / sticky sessions.
# Multi-replica deployments should front with ingress/API-gateway limits.
sdk_rate_limiter = SlidingWindowRateLimiter()

# Defaults (overridable via settings)
DEFAULT_SDK_LIMIT = 600  # per minute per identity
DEFAULT_AUTH_FAILURE_LIMIT = 30  # per minute per key
DEFAULT_EXPORT_LIMIT = 10  # per minute
DEFAULT_EVAL_TRIGGER_LIMIT = 20  # per minute
