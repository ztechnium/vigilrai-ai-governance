"""Instance access context derived from memberships.

This edition has one organization. Permissions come from the caller's
memberships, not from a selected tenant.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from rai_gateway.core.principal import Principal


@dataclass(frozen=True)
class TenantContext:
    """Server-resolved access context for the single instance."""

    principal: Principal
    membership_ids: tuple[UUID, ...]
    roles: tuple[str, ...]
    permissions: frozenset[str]

    @property
    def user_id(self) -> str:
        return self.principal.user_id

    @property
    def email(self) -> str:
        return self.principal.email

    def has_permission(self, permission: str) -> bool:
        return "*" in self.permissions or permission in self.permissions

    def has_any_permission(self, *permissions: str) -> bool:
        if "*" in self.permissions:
            return True
        return any(permission in self.permissions for permission in permissions)

    def has_role(self, role: str) -> bool:
        return role in self.roles

    def has_any_role(self, *roles: str) -> bool:
        return any(role in self.roles for role in roles)
