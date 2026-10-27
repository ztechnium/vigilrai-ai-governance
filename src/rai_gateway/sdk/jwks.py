"""JWKS fetch/cache for mandatory OIDC signature verification."""

from __future__ import annotations

import logging
import threading
import time
from typing import Any, Callable

import httpx

logger = logging.getLogger(__name__)

ALLOWED_OIDC_ALGORITHMS = frozenset(
    {"RS256", "RS384", "RS512", "ES256", "ES384", "ES512", "PS256", "PS384", "PS512"}
)

JwksFetcher = Callable[[str], dict[str, Any]]


class JwksCache:
    """Thread-safe JWKS cache keyed by issuer (or JWKS URL)."""

    def __init__(
        self,
        *,
        fetcher: JwksFetcher | None = None,
        ttl_seconds: int = 3600,
        timeout_seconds: float = 5.0,
    ) -> None:
        self._fetcher = fetcher or self._default_fetch
        self._ttl = ttl_seconds
        self._timeout = timeout_seconds
        self._lock = threading.Lock()
        self._entries: dict[str, tuple[float, dict[str, Any]]] = {}

    def _default_fetch(self, url: str) -> dict[str, Any]:
        response = httpx.get(url, timeout=self._timeout)
        response.raise_for_status()
        body = response.json()
        if not isinstance(body, dict) or "keys" not in body:
            raise ValueError("JWKS response missing keys")
        return body

    def get(self, cache_key: str) -> dict[str, Any] | None:
        with self._lock:
            entry = self._entries.get(cache_key)
            if not entry:
                return None
            expires_at, jwks = entry
            if expires_at < time.time():
                return None
            return jwks

    def put(self, cache_key: str, jwks: dict[str, Any]) -> None:
        with self._lock:
            self._entries[cache_key] = (time.time() + self._ttl, jwks)

    def invalidate(self, cache_key: str) -> None:
        with self._lock:
            self._entries.pop(cache_key, None)

    def resolve(
        self, cache_key: str, jwks_url: str, *, force_refresh: bool = False
    ) -> dict[str, Any]:
        if not force_refresh:
            cached = self.get(cache_key)
            if cached is not None:
                return cached
        jwks = self._fetcher(jwks_url)
        self.put(cache_key, jwks)
        return jwks

    def find_key(
        self, jwks: dict[str, Any], *, kid: str | None, alg: str | None
    ) -> dict[str, Any] | None:
        keys = jwks.get("keys") or []
        if not isinstance(keys, list):
            return None
        for key in keys:
            if not isinstance(key, dict):
                continue
            if kid and key.get("kid") != kid:
                continue
            if alg and key.get("alg") and key.get("alg") != alg:
                continue
            return key
        if kid is None and keys:
            first = keys[0]
            return first if isinstance(first, dict) else None
        return None
