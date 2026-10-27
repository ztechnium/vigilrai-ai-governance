"""ContentRule V2 schema, backfill, and CRUD compatibility."""

from __future__ import annotations

import os
import uuid
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text

from rai_gateway.policy.domain import (
    ContentEvaluationType,
    ContentFailureMode,
    ContentRemediationType,
    PolicyEffect,
    PolicyInterventionPoint,
)
from rai_gateway.policy.service import PolicyCollectionService

PROJECT_ROOT = Path(__file__).resolve().parents[2]
PARENT_REVISION = "f4a5b6c7d8e9"


@pytest.fixture()
def fresh_migration_db():
    raw_url = os.environ.get(
        "TEST_DATABASE_URL",
        "postgresql://rai_user:rai_password@localhost:5434/rai_gateway",
    )
    base_url = raw_url.split("?")[0]
    schema = f"content_v2_{uuid.uuid4().hex}"

    base_engine = create_engine(base_url)
    with base_engine.connect() as conn:
        conn.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{schema}"'))
        conn.commit()

    schema_url = f"{base_url}?options=-csearch_path%3D{schema}"
    yield schema_url

    with base_engine.connect() as conn:
        conn.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        conn.commit()
    base_engine.dispose()


def _configure_alembic(cfg: Config, database_url: str) -> None:
    cfg.set_main_option("sqlalchemy.url", database_url.replace("%", "%%"))
    os.environ["TEST_DATABASE_URL"] = database_url


def test_content_rule_v2_migration_backfills_intervention_points(
    fresh_migration_db,
) -> None:
    cfg = Config(str(PROJECT_ROOT / "alembic.ini"))
    _configure_alembic(cfg, fresh_migration_db)

    # Upgrade to parent of V2 migration, insert legacy row, then upgrade to head.
    command.upgrade(cfg, PARENT_REVISION)

    engine = create_engine(fresh_migration_db)
    with engine.begin() as conn:
        system_id = uuid.uuid4()
        collection_id = uuid.uuid4()
        rule_input = uuid.uuid4()
        rule_output = uuid.uuid4()
        rule_both = uuid.uuid4()

        conn.execute(
            text(
                """
                INSERT INTO ai_systems (
                    id, system_key, name, status, created_by
                ) VALUES (
                    :id, :system_key, 'V2 System', 'APPROVED', 'tester'
                )
                """
            ),
            {
                "id": system_id,
                "system_key": f"sys-{uuid.uuid4().hex[:8]}",
            },
        )
        conn.execute(
            text(
                """
                INSERT INTO policy_collections (id, ai_system_id, name, status)
                VALUES (:id, :ai_system_id, 'Default', 'ACTIVE')
                """
            ),
            {"id": collection_id, "ai_system_id": system_id},
        )
        for rule_id, applies_to in (
            (rule_input, "INPUT"),
            (rule_output, "OUTPUT"),
            (rule_both, "BOTH"),
        ):
            conn.execute(
                text(
                    """
                    INSERT INTO content_rules (
                        id, policy_collection_id, title, content, effect,
                        enabled, applies_to, rule_version
                    ) VALUES (
                        :id, :collection_id, :title, :content, 'MONITOR',
                        true, :applies_to, 1
                    )
                    """
                ),
                {
                    "id": rule_id,
                    "collection_id": collection_id,
                    "title": f"Rule {applies_to}",
                    "content": "legacy",
                    "applies_to": applies_to,
                },
            )

    command.upgrade(cfg, "head")

    with engine.connect() as conn:
        rows = list(
            conn.execute(
                text(
                    """
                    SELECT applies_to, intervention_points, evaluation_type,
                           failure_mode, remediation_type, content_targets
                    FROM content_rules
                    ORDER BY applies_to
                    """
                )
            ).mappings()
        )
        by_applies = {row["applies_to"]: row for row in rows}

        def _as_list(value):
            if isinstance(value, list):
                return value
            if isinstance(value, str):
                import json

                return json.loads(value)
            return list(value)

        assert _as_list(by_applies["INPUT"]["intervention_points"]) == ["INPUT"]
        assert _as_list(by_applies["OUTPUT"]["intervention_points"]) == ["OUTPUT"]
        assert set(_as_list(by_applies["BOTH"]["intervention_points"])) == {
            "INPUT",
            "OUTPUT",
        }

        meta = by_applies["BOTH"]
        assert meta["evaluation_type"] == "LLM_JUDGE"
        assert meta["failure_mode"] == "INHERIT"
        assert meta["remediation_type"] == "NONE"
        targets = meta["content_targets"]
        if isinstance(targets, str):
            import json

            targets = json.loads(targets)
        assert targets["mode"] == "FULL_CONTENT"

    engine.dispose()


def test_content_rule_v2_create_round_trip(db_session, policy_stack) -> None:
    svc = PolicyCollectionService(db_session)
    rule = svc.create_content_rule(
        policy_stack["system"].id,
        title="Block PII output",
        content="Do not emit customer PII.",
        effect=PolicyEffect.DENY.value,
        applies_to="OUTPUT",
        evaluation_type=ContentEvaluationType.DETECTOR.value,
        intervention_points=[
            PolicyInterventionPoint.OUTPUT.value,
            PolicyInterventionPoint.POST_MODEL.value,
        ],
        failure_mode=ContentFailureMode.FAIL_CLOSED.value,
        remediation_type=ContentRemediationType.REDACT.value,
        minimum_confidence=0.8,
        inline_enforcement_required=True,
        evaluation_timeout_ms=1500,
        actor="tester",
    )
    serialized = svc._serialize_content_rule(rule)
    assert serialized["evaluation_type"] == "DETECTOR"
    assert set(serialized["intervention_points"]) == {"OUTPUT", "POST_MODEL"}
    assert serialized["failure_mode"] == "FAIL_CLOSED"
    assert serialized["remediation_type"] == "REDACT"
    assert serialized["minimum_confidence"] == 0.8
    assert serialized["inline_enforcement_required"] is True
    assert serialized["evaluation_timeout_ms"] == 1500
    assert serialized["coverage_status"] == "NOT_CONFIGURED"
    assert serialized["applies_to"] == "OUTPUT"


def test_legacy_applies_to_only_create_still_works(db_session, policy_stack) -> None:
    svc = PolicyCollectionService(db_session)
    rule = svc.create_content_rule(
        policy_stack["system"].id,
        title="Legacy input rule",
        content="Watch user input.",
        effect=PolicyEffect.MONITOR.value,
        applies_to="INPUT",
        actor="tester",
    )
    serialized = svc._serialize_content_rule(rule)
    assert serialized["applies_to"] == "INPUT"
    assert serialized["intervention_points"] == ["INPUT"]
    assert serialized["evaluation_type"] == "LLM_JUDGE"
    assert serialized["failure_mode"] == "INHERIT"
    assert serialized["remediation_type"] == "NONE"
    assert serialized["content_targets"]["mode"] == "FULL_CONTENT"


def test_update_bumps_rule_version_on_governance_change(
    db_session, policy_stack
) -> None:
    svc = PolicyCollectionService(db_session)
    rule = svc.create_content_rule(
        policy_stack["system"].id,
        title="Versioned",
        content="v1",
        effect=PolicyEffect.MONITOR.value,
        actor="tester",
    )
    assert rule.rule_version == 1
    updated = svc.update_content_rule(
        rule.id,
        actor="tester",
        evaluation_type=ContentEvaluationType.REGEX.value,
    )
    assert updated.rule_version == 2
    assert updated.evaluation_type == "REGEX"
