"""Data-access authorization and runtime masking (Phase 2).

Enforcement must run at the data gateway / tool adapter / retrieval layer
*before* payloads reach the model. Evidence redaction alone is not sufficient.
"""

from __future__ import annotations

import hashlib
import re
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from rai_gateway.data_access.domain import (
    DEFAULT_FIELD_SENSITIVITY,
    PII_ALLOWED_PURPOSES,
    DataAccessDecision,
    DataAccessDecisionType,
    DataAccessRequest,
    DataSensitivity,
    FieldTransform,
)
from rai_gateway.models.data_access import DataAccessPolicy, DataAccessReceipt


def _enabled(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).lower() in {"1", "true", "yes", "y"}


def mask_value(value: Any, style: str = "REDACT") -> Any:
    if value is None:
        return None
    text = str(value)
    style = (style or "REDACT").upper()
    if style == "HASH":
        return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]
    if style == "LAST4":
        if len(text) <= 4:
            return "****"
        return ("*" * (len(text) - 4)) + text[-4:]
    # REDACT
    if "@" in text:
        local, _, domain = text.partition("@")
        return f"{local[:1]}***@{domain}"
    if len(text) <= 4:
        return "****"
    return text[:1] + ("*" * (len(text) - 2)) + text[-1:]


class DataAccessService:
    """Authorize and transform data before agent/model consumption."""

    def __init__(self, db: Session) -> None:
        self._db = db

    def create_policy(
        self,
        *,
        name: str,
        created_by: str,
        effect: str = DataAccessDecisionType.DENY.value,
        ai_system_id: UUID | None = None,
        data_source_id: UUID | None = None,
        resource: str | None = None,
        field_name: str | None = None,
        classification: str | None = None,
        purpose: str | None = None,
        access_mode: str | None = None,
        mask_style: str = "REDACT",
        row_predicate: dict[str, Any] | None = None,
        priority: int = 100,
    ) -> DataAccessPolicy:
        row = DataAccessPolicy(
            name=name,
            enabled="true",
            ai_system_id=ai_system_id,
            data_source_id=data_source_id,
            resource=resource,
            field_name=field_name,
            classification=classification,
            purpose=purpose,
            access_mode=access_mode,
            effect=effect,
            mask_style=mask_style,
            row_predicate=row_predicate,
            priority=str(priority),
            created_by=created_by,
        )
        self._db.add(row)
        self._db.commit()
        self._db.refresh(row)
        return row

    def authorize(
        self,
        request: DataAccessRequest,
        *,
        persist_receipt: bool = True,
        correlation_id: str | None = None,
    ) -> DataAccessDecision:
        fields = list(request.fields) or (
            list(request.payload.keys()) if isinstance(request.payload, dict) else []
        )
        policies = self._matching_policies(request)
        transforms: list[FieldTransform] = []
        allowed: list[str] = []
        denied: list[str] = []
        masked: list[str] = []
        rule_ids: list[str] = []
        row_filter = dict(request.row_filter or {})
        overall = DataAccessDecisionType.ALLOW
        reason = "DATA_ACCESS_ALLOWED"
        explanation = "All requested fields allowed"

        for field_name in fields:
            effect, style, rule_id = self._resolve_field(field_name, request, policies)
            if rule_id:
                rule_ids.append(rule_id)
            if effect == DataAccessDecisionType.DENY.value:
                denied.append(field_name)
                transforms.append(
                    FieldTransform(field=field_name, action="DROP", mask_style=style)
                )
                overall = DataAccessDecisionType.DENY
                reason = "DATA_FIELD_DENIED"
                explanation = f"Field '{field_name}' denied by data access policy"
            elif effect == DataAccessDecisionType.MASK.value:
                masked.append(field_name)
                allowed.append(field_name)
                transforms.append(
                    FieldTransform(field=field_name, action="MASK", mask_style=style)
                )
                if overall == DataAccessDecisionType.ALLOW:
                    overall = DataAccessDecisionType.MASK
                    reason = "DATA_FIELD_MASKED"
                    explanation = "Sensitive fields masked before agent receipt"
            elif effect == DataAccessDecisionType.REQUIRE_APPROVAL.value:
                denied.append(field_name)
                transforms.append(
                    FieldTransform(field=field_name, action="DROP", mask_style=style)
                )
                overall = DataAccessDecisionType.REQUIRE_APPROVAL
                reason = "DATA_ACCESS_APPROVAL_REQUIRED"
                explanation = f"Field '{field_name}' requires human approval"
            elif effect == DataAccessDecisionType.FILTER.value:
                allowed.append(field_name)
                if overall == DataAccessDecisionType.ALLOW:
                    overall = DataAccessDecisionType.FILTER
                    reason = "DATA_ROW_FILTERED"
                    explanation = "Row filter applied by data access policy"
            else:
                allowed.append(field_name)
                transforms.append(
                    FieldTransform(field=field_name, action="ALLOW", mask_style=style)
                )

        # Merge FILTER predicates from policies
        for pol in policies:
            if pol.effect == DataAccessDecisionType.FILTER.value and pol.row_predicate:
                row_filter = {**row_filter, **dict(pol.row_predicate)}

        # Hard deny if any denied and decision is DENY (not REQUIRE_APPROVAL)
        if denied and overall == DataAccessDecisionType.DENY:
            transformed = None
        else:
            transformed = self.apply_transforms(request.payload, transforms)

        decision = DataAccessDecision(
            decision=overall,
            reason_code=reason,
            human_explanation=explanation,
            allowed_fields=allowed,
            denied_fields=denied,
            masked_fields=masked,
            transforms=transforms,
            row_filter=row_filter,
            transformed_payload=transformed,
            policy_rule_ids=sorted(set(rule_ids)),
        )

        if persist_receipt:
            receipt = DataAccessReceipt(
                ai_system_id=request.ai_system_id,
                agent_id=request.agent_id,
                agent_version_id=request.agent_version_id,
                runtime_identity_id=request.runtime_identity_id,
                data_source_id=request.data_source_id,
                tool_id=request.tool_id,
                principal=request.principal,
                resource=request.resource,
                purpose=request.purpose,
                access_mode=request.access_mode,
                requested_fields=fields,
                allowed_fields=allowed,
                denied_fields=denied,
                masked_fields=masked,
                decision=overall.value,
                reason_code=reason,
                human_explanation=explanation,
                transforms=decision.to_dict()["transforms"],
                row_filter=row_filter,
                policy_rule_ids=decision.policy_rule_ids,
                correlation_id=correlation_id,
            )
            self._db.add(receipt)
            self._db.commit()
            self._db.refresh(receipt)
            decision.receipt_id = receipt.id

        return decision

    def apply_transforms(
        self,
        payload: dict[str, Any] | list[Any] | None,
        transforms: list[FieldTransform],
    ) -> dict[str, Any] | list[Any] | None:
        if payload is None:
            return None
        by_field = {t.field: t for t in transforms}

        def _one(row: dict[str, Any]) -> dict[str, Any]:
            out: dict[str, Any] = {}
            for key, value in row.items():
                t = by_field.get(key)
                if t is None:
                    # Unknown fields: if sensitive by catalog, mask by default
                    sens = DEFAULT_FIELD_SENSITIVITY.get(key.lower())
                    if sens in {
                        DataSensitivity.SENSITIVE_PII.value,
                        DataSensitivity.RESTRICTED.value,
                    }:
                        out[key] = mask_value(value, "REDACT")
                    else:
                        out[key] = value
                    continue
                if t.action == "DROP":
                    continue
                if t.action == "MASK":
                    out[key] = mask_value(value, t.mask_style)
                elif t.action == "HASH":
                    out[key] = mask_value(value, "HASH")
                else:
                    out[key] = value
            return out

        if isinstance(payload, list):
            return [_one(r) if isinstance(r, dict) else r for r in payload]
        if isinstance(payload, dict):
            return _one(payload)
        return payload

    def assert_no_raw_sensitive(
        self, payload: dict[str, Any] | list[Any] | None, *, fields: list[str]
    ) -> None:
        """Test helper / runtime guard: raw sensitive values must not appear."""
        if payload is None:
            return
        rows = payload if isinstance(payload, list) else [payload]
        for row in rows:
            if not isinstance(row, dict):
                continue
            for f in fields:
                if f in row and row[f] is not None:
                    raw = str(row[f])
                    if re.fullmatch(r"[A-Za-z0-9\-]+", raw) and "*" not in raw:
                        # Heuristic: unmasked alnum likely raw — only flag known sensitive
                        if f.lower() in DEFAULT_FIELD_SENSITIVITY:
                            if DEFAULT_FIELD_SENSITIVITY[f.lower()] in {
                                DataSensitivity.SENSITIVE_PII.value,
                                DataSensitivity.RESTRICTED.value,
                            }:
                                raise AssertionError(
                                    f"Raw sensitive field '{f}' leaked to agent payload"
                                )

    def _matching_policies(self, request: DataAccessRequest) -> list[DataAccessPolicy]:
        rows = (
            self._db.query(DataAccessPolicy)
            .order_by(DataAccessPolicy.priority.asc())
            .all()
        )
        matched: list[DataAccessPolicy] = []
        for row in rows:
            if not _enabled(row.enabled):
                continue
            if (
                row.ai_system_id
                and request.ai_system_id
                and row.ai_system_id != request.ai_system_id
            ):
                continue
            if (
                row.data_source_id
                and request.data_source_id
                and row.data_source_id != request.data_source_id
            ):
                continue
            if row.resource and row.resource != request.resource:
                continue
            if row.purpose and request.purpose and row.purpose != request.purpose:
                continue
            if row.access_mode and row.access_mode != request.access_mode:
                continue
            matched.append(row)
        return matched

    def _resolve_field(
        self,
        field_name: str,
        request: DataAccessRequest,
        policies: list[DataAccessPolicy],
    ) -> tuple[str, str, str | None]:
        # Explicit policy for this field wins (highest priority = lowest number already sorted)
        for pol in policies:
            if pol.field_name and pol.field_name.lower() == field_name.lower():
                return pol.effect, pol.mask_style or "REDACT", str(pol.id)
            if pol.field_name is None and pol.classification:
                sens = DEFAULT_FIELD_SENSITIVITY.get(field_name.lower())
                if sens == pol.classification:
                    return pol.effect, pol.mask_style or "REDACT", str(pol.id)

        # Built-in defaults for sensitive PII
        sens = DEFAULT_FIELD_SENSITIVITY.get(field_name.lower())
        if sens == DataSensitivity.SENSITIVE_PII.value:
            purpose = (request.purpose or "").lower()
            if purpose in PII_ALLOWED_PURPOSES:
                return DataAccessDecisionType.MASK.value, "LAST4", None
            return DataAccessDecisionType.DENY.value, "REDACT", None
        if sens in {
            DataSensitivity.PII.value,
            DataSensitivity.RESTRICTED.value,
        }:
            return DataAccessDecisionType.MASK.value, "REDACT", None
        return DataAccessDecisionType.ALLOW.value, "REDACT", None
