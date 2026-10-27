"""SaaS authentication domain types."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID


@dataclass(frozen=True)
class SessionTokens:
    access_token: str
    refresh_token: str
    session_id: UUID
    expires_at: datetime
    token_type: str = "bearer"


@dataclass(frozen=True)
class AuthenticatedSession:
    session_id: UUID
    user_id: str
    email: str
    name: str
    platform_roles: tuple[str, ...]
    authentication_assurance: str | None
    acr: str | None
    amr: tuple[str, ...]
    auth_time: int | None
    email_verified: bool
