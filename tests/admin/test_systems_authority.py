"""Authoritative AI system source tests for legacy admin systems endpoint."""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

from rai_gateway.core.config import settings
from rai_gateway.models.database import ExecutionAudit
from rai_gateway.registry.service import RegistryService


@pytest.fixture()
def admin_headers(monkeypatch: pytest.MonkeyPatch) -> dict[str, str]:
    token = "test-admin-token"
    monkeypatch.setattr(settings, "admin_token", token)
    return {"X-Admin-Token": token, "X-Admin-Role": "admin"}


def test_registered_system_exists_without_audit_activity(
    test_client: TestClient,
    db_session,
    admin_headers: dict[str, str],
    test_organization,
) -> None:
    registry = RegistryService(db_session)
    key = f"registered-only-{uuid.uuid4().hex[:8]}"
    registry.create_ai_system(
        system_key=key,
        name="Registered Only System",
        created_by="tester",
        owner_id="owner-1",
    )

    response = test_client.get("/admin/api/systems", headers=admin_headers)
    assert response.status_code == 200
    payload = response.json()
    match = next(item for item in payload if item["system_id"] == key)
    assert match["name"] == "Registered Only System"
    assert match["owner"] == "owner-1"
    assert match["registered"] is True
    assert match["execution_count"] == 0


def test_audit_event_does_not_create_authoritative_system(
    test_client: TestClient,
    db_session,
    admin_headers: dict[str, str],
    seed_prompt: dict[str, str],
    test_organization,
) -> None:
    observed_id = f"shadow-{uuid.uuid4().hex[:8]}"
    db_session.add(
        ExecutionAudit(
            execution_id=uuid.uuid4(),
            trace_id=str(uuid.uuid4()),
            prompt_id=seed_prompt["prompt_id"],
            prompt_version=seed_prompt["version"],
            system_id=observed_id,
            input_hash="hash",
            decision="ALLOW",
            policy_version="v1",
            guard_version="v1",
        )
    )
    db_session.commit()

    response = test_client.get("/admin/api/systems", headers=admin_headers)
    assert response.status_code == 200
    payload = response.json()
    observed = next(item for item in payload if item["system_id"] == observed_id)
    assert observed["registered"] is False
    assert observed["status"] == "OBSERVED_UNREGISTERED"
    assert observed["execution_count"] == 1


def test_registered_system_lifecycle_comes_from_registry(
    test_client: TestClient,
    db_session,
    admin_headers: dict[str, str],
    test_organization,
) -> None:
    registry = RegistryService(db_session)
    key = f"suspended-{uuid.uuid4().hex[:8]}"
    system = registry.create_ai_system(
        system_key=key,
        name="Suspended System",
        created_by="tester",
    )
    registry.transition_ai_system(system.id, "UNDER_REVIEW", updated_by="tester")
    registry.transition_ai_system(system.id, "APPROVED", updated_by="tester")
    registry.transition_ai_system(system.id, "SUSPENDED", updated_by="tester")

    response = test_client.get("/admin/api/systems", headers=admin_headers)
    match = next(item for item in response.json() if item["system_id"] == key)
    assert match["status"] == "SUSPENDED"
    assert match["registered"] is True
