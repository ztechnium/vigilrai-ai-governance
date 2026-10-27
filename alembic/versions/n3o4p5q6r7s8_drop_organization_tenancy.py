"""Drop multi-organization tenancy for the community edition.

Revision ID: n3o4p5q6r7s8
Revises: m2n3o4p5q6r7
Create Date: 2026-10-26 15:45:00.000000

Keeps memberships, departments, and a single governance profile.
Aborts when more than one organization row exists.
Idempotent when the organizations table is already gone.
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "n3o4p5q6r7s8"
down_revision: Union[str, None] = "m2n3o4p5q6r7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

CATALOG_KEYS = (
    ("tool_resources", "tool_key"),
    ("mcp_servers", "server_key"),
    ("external_services", "service_key"),
    ("data_sources", "data_source_key"),
)


def _tables() -> set[str]:
    return set(sa.inspect(op.get_bind()).get_table_names())


def _columns(table: str) -> set[str]:
    if table not in _tables():
        return set()
    return {col["name"] for col in sa.inspect(op.get_bind()).get_columns(table)}


def _exec(sql: str) -> None:
    op.execute(sa.text(sql))


def upgrade() -> None:
    bind = op.get_bind()
    tables = _tables()
    if "organizations" in tables:
        count = (
            bind.execute(sa.text("SELECT COUNT(*) FROM organizations")).scalar() or 0
        )
        if count > 1:
            raise RuntimeError(
                "Community edition cannot collapse more than one organization. "
                f"Found {count} organizations rows."
            )
        _move_org_identity_onto_profile()

    _drop_tenant_constraints()
    _drop_organization_id_columns()
    _add_singleton_keys()
    _add_global_uniques()

    if "organizations" in _tables():
        _exec("DROP TABLE IF EXISTS organizations CASCADE")


def _move_org_identity_onto_profile() -> None:
    cols = _columns("organization_governance_profiles")
    if "name" not in cols:
        op.add_column(
            "organization_governance_profiles",
            sa.Column("name", sa.String(), nullable=True),
        )
    if "description" not in cols:
        op.add_column(
            "organization_governance_profiles",
            sa.Column("description", sa.Text(), nullable=True),
        )
    if "logo" not in cols:
        op.add_column(
            "organization_governance_profiles",
            sa.Column("logo", sa.Text(), nullable=True),
        )
    if "organization_id" in _columns("organization_governance_profiles"):
        _exec(
            """
            UPDATE organization_governance_profiles AS profile
            SET name = org.name,
                description = org.description,
                logo = org.logo
            FROM organizations AS org
            WHERE profile.organization_id = org.id
            """
        )
    _exec(
        """
        UPDATE organization_governance_profiles
        SET name = 'Organization'
        WHERE name IS NULL
        """
    )


def _drop_tenant_constraints() -> None:
    fk_clause = ""
    if "organizations" in _tables():
        fk_clause = """
                    OR (
                        con.contype = 'f'
                        AND con.confrelid = 'organizations'::regclass
                    )
        """
    _exec(
        f"""
        DO $$
        DECLARE
            rec record;
        BEGIN
            FOR rec IN
                SELECT con.conname AS name, rel.relname AS table_name
                FROM pg_constraint con
                JOIN pg_class rel ON rel.oid = con.conrelid
                JOIN pg_namespace nsp ON nsp.oid = rel.relnamespace
                WHERE nsp.nspname = current_schema()
                  AND (
                    con.conname IN (
                        'uq_department_org_name',
                        'uq_org_membership_user_role',
                        'uq_ai_systems_organization_system_key',
                        'uq_sdk_integration_org_key',
                        'uq_sdk_decision_org_integration_idempotency',
                        'uq_runtime_conversation_org_key',
                        'uq_portfolio_report_schedule_scope',
                        'uq_portfolio_projection_org_key',
                        'uq_organizations_name_lower',
                        'uq_finops_metering_external_span',
                        'ck_policy_sources_scope_organization',
                        'ck_model_resources_scope_organization',
                        'ck_tool_resources_scope_organization',
                        'ck_mcp_servers_scope_organization',
                        'ck_external_services_scope_organization',
                        'ck_data_sources_scope_organization'
                    )
                    {fk_clause}
                  )
            LOOP
                EXECUTE format(
                    'ALTER TABLE %I DROP CONSTRAINT IF EXISTS %I',
                    rec.table_name,
                    rec.name
                );
            END LOOP;
        END $$;
        """
    )
    for index in (
        "uq_tool_resources_org_tool_key",
        "uq_mcp_servers_org_server_key",
        "uq_external_services_org_service_key",
        "uq_data_sources_org_data_source_key",
        "ix_finops_span_org_started",
        "ix_ai_systems_organization_id",
        "ix_ai_systems_organization_id_status",
        "ix_ai_systems_organization_id_updated_at",
        "uq_finops_metering_external_span",
    ):
        _exec(f'DROP INDEX IF EXISTS "{index}"')


def _drop_organization_id_columns() -> None:
    for table in sorted(_tables()):
        if "organization_id" not in _columns(table):
            continue
        _exec(
            f"""
            DO $$
            DECLARE
                rec record;
            BEGIN
                FOR rec IN
                    SELECT con.conname AS name
                    FROM pg_constraint con
                    JOIN pg_class rel ON rel.oid = con.conrelid
                    JOIN pg_attribute att ON att.attrelid = rel.oid
                        AND att.attnum = ANY (con.conkey)
                    WHERE rel.relname = '{table}'
                      AND att.attname = 'organization_id'
                LOOP
                    EXECUTE format(
                        'ALTER TABLE %I DROP CONSTRAINT IF EXISTS %I',
                        '{table}',
                        rec.name
                    );
                END LOOP;
            END $$;
            """
        )
        _exec(f'ALTER TABLE "{table}" DROP COLUMN IF EXISTS organization_id')


def _add_singleton_keys() -> None:
    if "organization_governance_profiles" in _tables():
        if "singleton_key" not in _columns("organization_governance_profiles"):
            op.add_column(
                "organization_governance_profiles",
                sa.Column("singleton_key", sa.String(), nullable=True),
            )
        _exec(
            """
            UPDATE organization_governance_profiles
            SET singleton_key = 'default'
            WHERE singleton_key IS NULL
            """
        )
        _exec(
            """
            ALTER TABLE organization_governance_profiles
            ALTER COLUMN singleton_key SET NOT NULL
            """
        )
        _exec(
            """
            ALTER TABLE organization_governance_profiles
            ALTER COLUMN name SET NOT NULL
            """
        )
        _exec(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS uq_governance_profile_singleton
            ON organization_governance_profiles (singleton_key)
            """
        )
    if "organization_onboarding" in _tables():
        if "singleton_key" not in _columns("organization_onboarding"):
            op.add_column(
                "organization_onboarding",
                sa.Column("singleton_key", sa.String(), nullable=True),
            )
        _exec(
            """
            UPDATE organization_onboarding
            SET singleton_key = 'default'
            WHERE singleton_key IS NULL
            """
        )
        _exec(
            """
            ALTER TABLE organization_onboarding
            ALTER COLUMN singleton_key SET NOT NULL
            """
        )
        _exec(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS uq_onboarding_singleton
            ON organization_onboarding (singleton_key)
            """
        )


def _add_global_uniques() -> None:
    statements = [
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_department_name
        ON departments (name)
        """,
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_membership_user_role
        ON organization_memberships (user_id, role)
        """,
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_ai_systems_system_key
        ON ai_systems (system_key)
        """,
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_sdk_integration_key
        ON sdk_integrations (integration_key)
        """,
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_sdk_decision_integration_idempotency
        ON sdk_decision_records (integration_id, idempotency_key)
        """,
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_runtime_conversation_key
        ON runtime_conversations (conversation_key)
        """,
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_portfolio_report_schedule_scope
        ON portfolio_report_schedules (cadence, scope_type, scope_id)
        """,
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_portfolio_projection_key
        ON portfolio_projection_state (projection_key)
        """,
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_finops_metering_external_span
        ON finops_metering_spans (external_span_id)
        WHERE external_span_id IS NOT NULL
        """,
        """
        CREATE INDEX IF NOT EXISTS ix_finops_span_started
        ON finops_metering_spans (started_at)
        """,
    ]
    tables = _tables()
    required = {
        "uq_department_name": "departments",
        "uq_membership_user_role": "organization_memberships",
        "uq_ai_systems_system_key": "ai_systems",
        "uq_sdk_integration_key": "sdk_integrations",
        "uq_sdk_decision_integration_idempotency": "sdk_decision_records",
        "uq_runtime_conversation_key": "runtime_conversations",
        "uq_portfolio_report_schedule_scope": "portfolio_report_schedules",
        "uq_portfolio_projection_key": "portfolio_projection_state",
        "uq_finops_metering_external_span": "finops_metering_spans",
        "ix_finops_span_started": "finops_metering_spans",
    }
    for sql in statements:
        name = sql.split("IF NOT EXISTS", 1)[1].split()[0].strip()
        if required.get(name) in tables:
            _exec(sql)
    for table, key_col in CATALOG_KEYS:
        if table not in tables:
            continue
        _exec(
            f"""
            CREATE UNIQUE INDEX IF NOT EXISTS uq_{table}_instance_{key_col}
            ON {table} ({key_col})
            WHERE scope = 'ORGANIZATION'
            """
        )


def downgrade() -> None:
    raise RuntimeError(
        "The community edition single-organization migration cannot be reversed."
    )
