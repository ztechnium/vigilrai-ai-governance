"""Server-authoritative approver authorization for WP3."""

from __future__ import annotations

import time
from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from rai_gateway.approval.domain import ApprovalDenialCode
from rai_gateway.approval.errors import ApprovalDeniedError
from rai_gateway.core.config import settings
from rai_gateway.models.approval import ApprovalRequest
from rai_gateway.services.admin_console import _normalize_role, _resolve_permissions

STEP_UP_RISK_TIERS = frozenset({"CRITICAL"})
STEP_UP_VERIFIED = "step_up_verified"


@dataclass
class ApproverContext:
    """Approver identity and *server-derived* authentication assurance.

    Callers must never accept client-declared assurance as authoritative.
    Populate acr/amr/auth_time/authentication_assurance from verified
    admin session claims or server step-up verification only.
    """

    actor: str
    role: str
    authentication_assurance: str | None = None
    acr: str | None = None
    amr: list[str] = field(default_factory=list)
    auth_time: int | None = None


class ApproverAuthorizationService:
    """Authorize approvers using server-derived RBAC and IdP assurance."""

    def __init__(self, db: Session) -> None:
        self._db = db

    def authorize_approve(
        self,
        request: ApprovalRequest,
        approver: ApproverContext,
    ) -> None:
        self._require_approve_capability(approver.role)
        self._check_separation_of_duties(request, approver.actor)
        self._check_step_up(request, approver)

    def authorize_reject(
        self,
        request: ApprovalRequest,
        approver: ApproverContext,
    ) -> None:
        self._require_approve_capability(approver.role)
        self._check_separation_of_duties(request, approver.actor)

    def _require_approve_capability(self, role: str) -> None:
        """Check RolePermission catalog for approvals:approve (not identity auth).

        ``role`` may be a governance membership role (e.g. BUSINESS_APPROVER) or
        an RBAC role id. HTTP routes must still gate with
        ``require_permission("approvals:approve")`` and resolve the acting
        membership before invoking the approval service.
        """
        from rai_gateway.core.authorization import TENANT_ROLE_TO_RBAC_ROLE

        role_id = _normalize_role(TENANT_ROLE_TO_RBAC_ROLE.get(role, role))
        if not role_id:
            raise ApprovalDeniedError(
                ApprovalDenialCode.APPROVER_NOT_AUTHORIZED,
                "Approver role is required",
            )
        permissions = _resolve_permissions(self._db, role_id)
        if "*" not in permissions and "approvals:approve" not in permissions:
            raise ApprovalDeniedError(
                ApprovalDenialCode.APPROVER_NOT_AUTHORIZED,
                "Role does not have approvals:approve permission",
            )

    def _check_separation_of_duties(self, request: ApprovalRequest, actor: str) -> None:
        if request.initiating_principal and request.initiating_principal == actor:
            raise ApprovalDeniedError(
                ApprovalDenialCode.SELF_APPROVAL_DENIED,
                "Initiator cannot approve their own action (separation of duties)",
            )

    def _check_step_up(
        self, request: ApprovalRequest, approver: ApproverContext
    ) -> None:
        if not request.risk_tier or request.risk_tier.upper() not in STEP_UP_RISK_TIERS:
            return
        if not self._assurance_satisfied(approver):
            raise ApprovalDeniedError(
                ApprovalDenialCode.APPROVAL_STEP_UP_REQUIRED,
                "Additional authentication assurance required for CRITICAL risk approvals",
            )

    def _assurance_satisfied(self, approver: ApproverContext) -> bool:
        min_acr = settings.approval_minimum_acr
        if min_acr and (approver.acr or "") != min_acr:
            return False

        required_amr = settings.approval_required_amr
        if required_amr:
            needed = {p.strip() for p in required_amr.split(",") if p.strip()}
            have = set(approver.amr or [])
            if needed and not needed.issubset(have):
                return False

        max_age = settings.approval_max_auth_age_seconds
        if max_age is not None:
            if approver.auth_time is None:
                return False
            if int(time.time()) - int(approver.auth_time) > int(max_age):
                return False

        # Configured ACR/AMR policy is authoritative when present.
        if min_acr or required_amr:
            return True

        # Default CRITICAL policy: require server-derived step_up_verified.
        return approver.authentication_assurance == STEP_UP_VERIFIED
