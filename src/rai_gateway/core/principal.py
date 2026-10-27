"""Server-verified human principal for SaaS authentication."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from rai_gateway.core.auth import AdminIdentity


@dataclass(frozen=True)
class Principal:
    """Authenticated human identity.

    Identity fields must come from a server-verified session — never from
    request body claims.
    """

    user_id: str
    email: str
    session_id: str | None
    platform_roles: tuple[str, ...]
    authentication_assurance: str | None = None
    acr: str | None = None
    amr: tuple[str, ...] = ()
    auth_time: int | None = None

    def has_platform_role(self, role: str) -> bool:
        return role in self.platform_roles

    def is_platform_admin(self) -> bool:
        return "platform_admin" in self.platform_roles or "admin" in self.platform_roles

    @classmethod
    def from_admin_identity(
        cls,
        identity: AdminIdentity,
        *,
        session_id: str | None = None,
    ) -> Principal:
        """Compatibility bridge from legacy AdminIdentity sessions."""
        return cls(
            user_id=identity.user_id,
            email=identity.email,
            session_id=session_id,
            platform_roles=tuple(identity.roles or ()),
            authentication_assurance=identity.authentication_assurance,
            acr=identity.acr,
            amr=tuple(identity.amr or ()),
            auth_time=identity.auth_time,
        )
