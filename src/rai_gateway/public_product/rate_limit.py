"""In-memory rate limiting for public registration."""

from __future__ import annotations

from rai_gateway.sdk.rate_limit import SlidingWindowRateLimiter

registration_rate_limiter = SlidingWindowRateLimiter()

DEFAULT_REGISTER_LIMIT = 5
DEFAULT_REGISTER_WINDOW_SECONDS = 3600.0
