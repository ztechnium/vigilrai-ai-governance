"""WP5 retention and legal-hold behavior."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from rai_gateway.evidence.domain import EvidenceEventType, EvidenceSourceType
from rai_gateway.evidence.retention import (
    EvidenceRetentionError,
    EvidenceRetentionService,
)
from rai_gateway.evidence.service import TrajectoryService


def _trajectory(db_session, runtime_stack):
    svc = TrajectoryService(db_session)
    trajectory = svc.get_or_create_trajectory(
        ai_system_id=runtime_stack["system"].id,
        agent_id=runtime_stack["agent"].id,
        agent_version_id=runtime_stack["version"].id,
        runtime_identity_id=runtime_stack["identity"].id,
        conversation_id="conv-ret-1",
        correlation_id="corr-ret-1",
    )
    svc.append_event(
        trajectory,
        event_type=EvidenceEventType.SESSION_STARTED.value,
        source_type=EvidenceSourceType.RAI_AUTHORITATIVE.value,
        source_reference="ret:session",
        payload={"ok": True},
    )
    db_session.commit()
    return trajectory


class TestEvidenceRetention:
    def test_not_expired_cannot_purge(self, db_session, runtime_stack):
        trajectory = _trajectory(db_session, runtime_stack)
        retention = EvidenceRetentionService(db_session)
        retention.apply_defaults(trajectory)
        db_session.commit()
        eligible, code = retention.is_purge_eligible(trajectory)
        assert eligible is False
        assert code == "NOT_EXPIRED"
        with pytest.raises(EvidenceRetentionError) as exc:
            retention.purge_trajectory(trajectory.id, actor="tester")
        assert exc.value.code == "NOT_EXPIRED"

    def test_expired_eligible_and_purge(self, db_session, runtime_stack):
        trajectory = _trajectory(db_session, runtime_stack)
        retention = EvidenceRetentionService(db_session)
        past = datetime.now(timezone.utc) - timedelta(days=1)
        retention.set_retention(trajectory.id, retention_days=0, actor="tester")
        # Force eligibility into the past for deterministic tests.
        traj = TrajectoryService(db_session).get_trajectory(trajectory.id)
        assert traj is not None
        traj.eligible_for_purge_at = past
        db_session.commit()

        eligible, code = retention.is_purge_eligible(traj)
        assert eligible is True
        assert code == "ELIGIBLE"
        result = retention.purge_trajectory(traj.id, actor="tester")
        assert result["deleted"]["events"] >= 1
        assert TrajectoryService(db_session).get_trajectory(trajectory.id) is None

    def test_legal_hold_blocks_purge(self, db_session, runtime_stack):
        trajectory = _trajectory(db_session, runtime_stack)
        retention = EvidenceRetentionService(db_session)
        past = datetime.now(timezone.utc) - timedelta(days=1)
        trajectory.eligible_for_purge_at = past
        trajectory.retention_days = 0
        db_session.commit()
        retention.set_legal_hold(trajectory.id, legal_hold=True, actor="tester")
        traj = TrajectoryService(db_session).get_trajectory(trajectory.id)
        eligible, code = retention.is_purge_eligible(traj)
        assert eligible is False
        assert code == "LEGAL_HOLD_ACTIVE"
        with pytest.raises(EvidenceRetentionError) as exc:
            retention.purge_trajectory(traj.id, actor="tester")
        assert exc.value.code == "LEGAL_HOLD_ACTIVE"

        retention.set_legal_hold(trajectory.id, legal_hold=False, actor="tester")
        traj = TrajectoryService(db_session).get_trajectory(trajectory.id)
        eligible, code = retention.is_purge_eligible(traj)
        assert eligible is True
        assert code == "ELIGIBLE"


class TestRetentionApiAuth:
    def _auditor_headers(
        self,
        test_client,
        db_session,
        test_organization,
        monkeypatch: pytest.MonkeyPatch,
    ) -> dict:
        from datetime import datetime, timezone
        from uuid import uuid4

        from rai_gateway.auth.passwords import hash_password
        from rai_gateway.core.config import settings
        from rai_gateway.governance.domain import GovernanceRole, MembershipStatus
        from rai_gateway.models.database import AdminCredential, UserAccount
        from rai_gateway.models.governance import OrganizationMembership
        from rai_gateway.services.admin_console import _ensure_default_rbac_seed

        _ensure_default_rbac_seed(db_session)
        suffix = uuid4().hex[:8]
        email = f"auditor-{suffix}@example.com"
        user_id = f"auditor-{suffix}"
        db_session.add(
            UserAccount(
                user_id=user_id,
                email=email,
                name="Auditor",
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
        db_session.add(
            OrganizationMembership(
                user_id=user_id,
                role=GovernanceRole.AUDITOR.value,
                status=MembershipStatus.ACTIVE.value,
                created_by=user_id,
            )
        )
        db_session.commit()

        login = test_client.post(
            "/v1/auth/login",
            json={"email": email, "password": "SecurePass123!"},
        )
        assert login.status_code == 200, login.text
        monkeypatch.setattr(settings, "admin_token", None)
        return {
            "Authorization": f"Bearer {login.json()['access_token']}",
        }

    def test_auditor_cannot_purge(
        self, test_client, db_session, runtime_stack, test_organization, monkeypatch
    ):
        trajectory = _trajectory(db_session, runtime_stack)
        headers = self._auditor_headers(
            test_client, db_session, test_organization, monkeypatch
        )
        resp = test_client.post(
            f"/v1/trajectories/{trajectory.id}/purge",
            headers=headers,
            json={"reason": "test"},
        )
        assert resp.status_code == 403
        body = resp.json()
        assert body.get("error") == "NOT_ALLOWED"
        assert body.get("details", {}).get("required_permission") == "evidence:manage"

    def test_auditor_cannot_set_legal_hold(
        self, test_client, db_session, runtime_stack, test_organization, monkeypatch
    ):
        trajectory = _trajectory(db_session, runtime_stack)
        headers = self._auditor_headers(
            test_client, db_session, test_organization, monkeypatch
        )
        resp = test_client.post(
            f"/v1/trajectories/{trajectory.id}/legal-hold",
            headers=headers,
            json={"legal_hold": True},
        )
        assert resp.status_code == 403

    def test_auditor_can_read_trajectory(
        self, test_client, db_session, runtime_stack, test_organization, monkeypatch
    ):
        trajectory = _trajectory(db_session, runtime_stack)
        headers = self._auditor_headers(
            test_client, db_session, test_organization, monkeypatch
        )
        resp = test_client.get(
            f"/v1/trajectories/{trajectory.id}",
            headers=headers,
        )
        assert resp.status_code == 200
        assert resp.json()["id"] == str(trajectory.id)
