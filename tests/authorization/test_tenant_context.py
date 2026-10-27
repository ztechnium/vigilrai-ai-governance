"""Membership access context for the single-organization edition."""

from __future__ import annotations

import uuid

import pytest

from rai_gateway.core.authorization import (
    resolve_acting_membership,
    resolve_tenant_context,
)
from rai_gateway.core.errors import ErrorCode, RaiException
from rai_gateway.core.principal import Principal
from rai_gateway.governance.domain import GovernanceRole, MembershipStatus
from rai_gateway.models.governance import OrganizationMembership
from rai_gateway.services.admin_console import _ensure_default_rbac_seed


def _principal(user_id: str) -> Principal:
    return Principal(
        user_id=user_id,
        email=f"{user_id}@example.com",
        session_id=None,
        platform_roles=(),
    )


def test_user_without_membership_is_denied(db_session):
    _ensure_default_rbac_seed(db_session)
    with pytest.raises(RaiException) as exc:
        resolve_tenant_context(db_session, _principal("nobody"))
    assert exc.value.error_code == ErrorCode.NOT_ALLOWED


def test_admin_membership_maps_permissions(db_session):
    _ensure_default_rbac_seed(db_session)
    user_id = f"user-{uuid.uuid4().hex[:8]}"
    membership = OrganizationMembership(
        user_id=user_id,
        role=GovernanceRole.ORGANIZATION_ADMIN.value,
        status=MembershipStatus.ACTIVE.value,
        created_by=user_id,
    )
    db_session.add(membership)
    db_session.commit()

    tenant = resolve_tenant_context(db_session, _principal(user_id))
    assert GovernanceRole.ORGANIZATION_ADMIN.value in tenant.roles
    assert tenant.has_permission("registry:write")
    assert membership.id in tenant.membership_ids


def test_acting_membership_must_belong_to_the_caller(db_session):
    _ensure_default_rbac_seed(db_session)
    user_id = f"user-{uuid.uuid4().hex[:8]}"
    membership = OrganizationMembership(
        user_id=user_id,
        role=GovernanceRole.RAI_OFFICER.value,
        status=MembershipStatus.ACTIVE.value,
        created_by=user_id,
    )
    db_session.add(membership)
    db_session.commit()
    tenant = resolve_tenant_context(db_session, _principal(user_id))

    resolved = resolve_acting_membership(
        db_session,
        tenant,
        membership.id,
        allowed_roles=(GovernanceRole.RAI_OFFICER.value,),
    )
    assert resolved.id == membership.id

    with pytest.raises(RaiException):
        resolve_acting_membership(
            db_session,
            tenant,
            uuid.uuid4(),
        )
