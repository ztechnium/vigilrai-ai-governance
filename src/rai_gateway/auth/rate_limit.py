"""Rate limits for auth email endpoints."""

from __future__ import annotations

from rai_gateway.sdk.rate_limit import SlidingWindowRateLimiter

email_auth_rate_limiter = SlidingWindowRateLimiter()

RESEND_VERIFICATION_LIMIT = 5
RESEND_VERIFICATION_WINDOW_SECONDS = 3600.0

FORGOT_PASSWORD_LIMIT = 5
FORGOT_PASSWORD_WINDOW_SECONDS = 3600.0

RESET_PASSWORD_LIMIT = 10
RESET_PASSWORD_WINDOW_SECONDS = 3600.0
