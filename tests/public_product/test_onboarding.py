"""Organization onboarding API tests."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from rai_gateway.auth.passwords import hash_password
from rai_gateway.core.database import get_db
from rai_gateway.governance.domain import GovernanceRole, MembershipStatus
from rai_gateway.governance.service import GovernanceService
from rai_gateway.main import app
from rai_gateway.models.database import AdminCredential, UserAccount
from rai_gateway.models.governance import (
    OrganizationGovernanceProfile,
    OrganizationMembership,
)
from rai_gateway.models.productization import OrganizationOnboarding
from rai_gateway.public_product.onboarding import OnboardingService
from rai_gateway.services.admin_console import _ensure_default_rbac_seed


@pytest.fixture()
def public_client(db_session):
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)
    try:
        yield client
    finally:
        app.dependency_overrides.pop(get_db, None)


@pytest.fixture()
def auth_headers(public_client, db_session) -> dict[str, str]:
    _ensure_default_rbac_seed(db_session)
    suffix = uuid.uuid4().hex[:8]
    email = f"onboard-{suffix}@example.com"
    user_id = f"user-{suffix}"
    db_session.add(
        UserAccount(
            user_id=user_id,
            email=email,
            name="Onboard User",
            status="active",
            email_verified_at=datetime.now(timezone.utc),
        )
    )
    db_session.flush()
    db_session.add(
        AdminCredential(
            email=email,
            user_id=user_id,
            password_hash=hash_password("SecurePass123!"),
            is_active=True,
        )
    )
    for role in (
        GovernanceRole.ORGANIZATION_ADMIN.value,
        GovernanceRole.RAI_OFFICER.value,
    ):
        db_session.add(
            OrganizationMembership(
                user_id=user_id,
                role=role,
                status=MembershipStatus.ACTIVE.value,
                created_by=user_id,
            )
        )
    db_session.commit()
    login = public_client.post(
        "/v1/auth/login",
        json={"email": email, "password": "SecurePass123!"},
    )
    assert login.status_code == 200, login.text
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


def test_get_onboarding_returns_full_checklist(public_client, auth_headers):
    response = public_client.get("/v1/productization/onboarding", headers=auth_headers)
    assert response.status_code == 200, response.text
    body = response.json()
    assert len(body["steps"]) == 13
    assert "onboarding" in body
    assert body["onboarding"]["welcome_completed"] is False


def test_patch_onboarding_updates_state(public_client, db_session, auth_headers):
    response = public_client.patch(
        "/v1/productization/onboarding",
        json={
            "complete_step": "team_roles",
            "current_step": "first_ai_system",
            "status": "IN_PROGRESS",
        },
        headers=auth_headers,
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["onboarding"]["current_step"] == "first_ai_system"
    assert "team_roles" in body["onboarding"]["completed_steps"]

    record = (
        db_session.query(OrganizationOnboarding)
        .filter(OrganizationOnboarding.singleton_key == "default")
        .first()
    )
    assert record is not None
    assert record.current_step == "first_ai_system"


def test_public_onboarding_routes_removed(public_client):
    assert public_client.get("/v1/public/onboarding").status_code == 404
    assert (
        public_client.patch(
            "/v1/public/onboarding",
            json={"complete_step": "team_roles"},
        ).status_code
        == 404
    )


def test_onboarding_service_merges_computed_steps(db_session):
    profile = (
        db_session.query(OrganizationGovernanceProfile)
        .filter(OrganizationGovernanceProfile.singleton_key == "default")
        .first()
    )
    if profile is None:
        profile = OrganizationGovernanceProfile(
            singleton_key="default",
            name="Organization",
            legal_name="Organization",
        )
        db_session.add(profile)
        db_session.commit()

    gov = GovernanceService(db_session)
    suffix = uuid.uuid4().hex[:8]
    gov.patch_governance_profile(
        updated_by="tester",
        sector="Healthcare",
        jurisdiction="DE",
    )
    gov.create_membership(
        user_id=f"admin-{suffix}",
        role=GovernanceRole.ORGANIZATION_ADMIN.value,
        created_by="tester",
        status=MembershipStatus.ACTIVE.value,
    )
    gov.create_membership(
        user_id=f"officer-{suffix}",
        role=GovernanceRole.RAI_OFFICER.value,
        created_by="tester",
        status=MembershipStatus.ACTIVE.value,
    )

    checklist = OnboardingService(db_session).build_checklist()
    step_map = {step["id"]: step["done"] for step in checklist["steps"]}
    assert step_map["organization_profile"] is True
    assert step_map["team_roles"] is True
