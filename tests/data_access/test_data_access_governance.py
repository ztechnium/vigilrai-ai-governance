"""Phase 2 data-access governance — masking before agent receives data."""

from __future__ import annotations

import uuid

from rai_gateway.data_access.domain import (
    DataAccessDecisionType,
    DataAccessRequest,
)
from rai_gateway.data_access.service import DataAccessService, mask_value


def test_mask_value_styles():
    assert "*" in str(mask_value("29801011234567", "REDACT"))
    assert mask_value("123456789", "LAST4").endswith("6789")
    assert len(mask_value("secret", "HASH")) == 16


def test_national_id_denied_by_default(db_session):
    svc = DataAccessService(db_session)
    rid = uuid.uuid4()
    decision = svc.authorize(
        DataAccessRequest(
            runtime_identity_id=rid,
            agent_version_id=uuid.uuid4(),
            principal="agent",
            data_source_id=None,
            resource="customers",
            fields=["national_id", "email", "city"],
            purpose="sales_outreach",
            payload={
                "national_id": "29801011234567",
                "email": "a@example.com",
                "city": "Cairo",
            },
        )
    )
    assert decision.decision == DataAccessDecisionType.DENY
    assert "national_id" in decision.denied_fields
    assert "email" in decision.masked_fields or "email" in decision.allowed_fields
    assert decision.receipt_id is not None
    # Denied fields must not appear in transformed payload
    assert decision.transformed_payload is None or "national_id" not in (
        decision.transformed_payload or {}
    )


def test_national_id_masked_for_kyc_purpose(db_session):
    svc = DataAccessService(db_session)
    decision = svc.authorize(
        DataAccessRequest(
            runtime_identity_id=uuid.uuid4(),
            agent_version_id=uuid.uuid4(),
            principal="kyc-bot",
            data_source_id=None,
            resource="customers",
            fields=["national_id", "full_name"],
            purpose="kyc",
            payload={
                "national_id": "29801011234567",
                "full_name": "Ada Lovelace",
            },
        )
    )
    assert decision.decision == DataAccessDecisionType.MASK
    assert "national_id" in decision.masked_fields
    transformed = decision.transformed_payload
    assert isinstance(transformed, dict)
    assert transformed["national_id"] != "29801011234567"
    assert "*" in str(transformed["national_id"]) or transformed[
        "national_id"
    ].endswith("4567")
    # Model/agent never receives raw national_id
    assert "29801011234567" not in str(transformed)


def test_explicit_policy_mask_overrides(db_session):
    svc = DataAccessService(db_session)
    svc.create_policy(
        name="mask email always",
        created_by="tester",
        field_name="email",
        effect=DataAccessDecisionType.MASK.value,
        mask_style="REDACT",
        priority=10,
    )
    decision = svc.authorize(
        DataAccessRequest(
            runtime_identity_id=uuid.uuid4(),
            agent_version_id=uuid.uuid4(),
            principal="agent",
            data_source_id=None,
            resource="leads",
            fields=["email", "company"],
            purpose="sales_outreach",
            payload={"email": "ceo@acme.com", "company": "Acme"},
        )
    )
    assert decision.decision == DataAccessDecisionType.MASK
    assert decision.transformed_payload["email"] != "ceo@acme.com"
    assert decision.transformed_payload["company"] == "Acme"


def test_row_filter_policy(db_session):
    svc = DataAccessService(db_session)
    svc.create_policy(
        name="region filter",
        created_by="tester",
        resource="orders",
        effect=DataAccessDecisionType.FILTER.value,
        row_predicate={"region": "eu-1"},
        priority=50,
    )
    decision = svc.authorize(
        DataAccessRequest(
            runtime_identity_id=uuid.uuid4(),
            agent_version_id=uuid.uuid4(),
            principal="agent",
            data_source_id=None,
            resource="orders",
            fields=["order_id"],
            purpose="support",
            payload={"order_id": "O-1"},
        )
    )
    assert decision.decision in {
        DataAccessDecisionType.FILTER,
        DataAccessDecisionType.ALLOW,
    }
    assert decision.row_filter.get("region") == "eu-1"
