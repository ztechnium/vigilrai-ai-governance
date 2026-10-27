"""wp8_governance_pilot_operating_model

Revision ID: m8n9o0p1q2r3
Revises: l6m7n8o9p0q1
Create Date: 2026-09-14 17:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "m8n9o0p1q2r3"
down_revision: Union[str, None] = "l6m7n8o9p0q1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "organization_governance_profiles",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "singleton_key",
            sa.String(),
            nullable=False,
            server_default=sa.text("'default'"),
        ),
        sa.Column(
            "name",
            sa.String(),
            nullable=False,
            server_default=sa.text("'Organization'"),
        ),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("legal_name", sa.String(), nullable=True),
        sa.Column("organization_type", sa.String(), nullable=False),
        sa.Column("sector", sa.String(), nullable=True),
        sa.Column("jurisdiction", sa.String(), nullable=True),
        sa.Column("regulatory_context", sa.JSON(), nullable=True),
        sa.Column("risk_appetite", sa.String(), nullable=True),
        sa.Column("governance_owner", sa.String(), nullable=True),
        sa.Column("assurance_owner", sa.String(), nullable=True),
        sa.Column("incident_owner", sa.String(), nullable=True),
        sa.Column("default_review_frequency_days", sa.Integer(), nullable=False),
        sa.Column("evidence_retention_policy", sa.JSON(), nullable=True),
        sa.Column("pilot_status", sa.String(), nullable=False),
        sa.Column("updated_by", sa.String(), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=True,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("singleton_key", name="uq_governance_profile_singleton"),
    )
    op.create_index(
        "ix_organization_governance_profiles_pilot_status",
        "organization_governance_profiles",
        ["pilot_status"],
    )

    op.create_table(
        "organization_memberships",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("role", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column(
            "valid_from",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=True,
        ),
        sa.Column("valid_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", sa.String(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=True,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "user_id",
            "role",
            name="uq_membership_user_role",
        ),
    )
    op.create_index(
        "ix_organization_memberships_user_id", "organization_memberships", ["user_id"]
    )
    op.create_index(
        "ix_organization_memberships_role", "organization_memberships", ["role"]
    )
    op.create_index(
        "ix_organization_memberships_status", "organization_memberships", ["status"]
    )

    op.create_table(
        "control_frameworks",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("framework_key", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("version", sa.String(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("is_internal", sa.Boolean(), nullable=False),
        sa.Column("published", sa.Boolean(), nullable=False),
        sa.Column("created_by", sa.String(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=True,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("framework_key"),
    )
    op.create_index(
        "ix_control_frameworks_framework_key", "control_frameworks", ["framework_key"]
    )

    op.create_table(
        "control_objectives",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("framework_id", sa.UUID(), nullable=False),
        sa.Column("code", sa.String(), nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("category", sa.String(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=True,
        ),
        sa.ForeignKeyConstraint(["framework_id"], ["control_frameworks.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("framework_id", "code", name="uq_control_objective_code"),
    )
    op.create_index(
        "ix_control_objectives_framework_id", "control_objectives", ["framework_id"]
    )
    op.create_index("ix_control_objectives_code", "control_objectives", ["code"])
    op.create_index(
        "ix_control_objectives_category", "control_objectives", ["category"]
    )

    op.create_table(
        "control_requirements",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("objective_id", sa.UUID(), nullable=False),
        sa.Column("requirement_key", sa.String(), nullable=False),
        sa.Column("statement", sa.Text(), nullable=False),
        sa.Column("default_applicability", sa.String(), nullable=False),
        sa.Column("applicability_rules", sa.JSON(), nullable=True),
        sa.Column("automated_check", sa.String(), nullable=True),
        sa.Column("non_waivable", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=True,
        ),
        sa.ForeignKeyConstraint(["objective_id"], ["control_objectives.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_control_requirements_objective_id",
        "control_requirements",
        ["objective_id"],
    )
    op.create_index(
        "ix_control_requirements_requirement_key",
        "control_requirements",
        ["requirement_key"],
    )

    op.create_table(
        "control_mappings",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("internal_requirement_id", sa.UUID(), nullable=False),
        sa.Column("external_framework", sa.String(), nullable=False),
        sa.Column("external_requirement_id", sa.String(), nullable=False),
        sa.Column("external_requirement_title", sa.String(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=True,
        ),
        sa.ForeignKeyConstraint(
            ["internal_requirement_id"], ["control_requirements.id"]
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_control_mappings_internal_requirement_id",
        "control_mappings",
        ["internal_requirement_id"],
    )
    op.create_index(
        "ix_control_mappings_external_framework",
        "control_mappings",
        ["external_framework"],
    )

    op.create_table(
        "ai_system_accountabilities",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("ai_system_id", sa.UUID(), nullable=False),
        sa.Column("business_owner_membership_id", sa.UUID(), nullable=True),
        sa.Column("technical_owner_membership_id", sa.UUID(), nullable=True),
        sa.Column("rai_officer_membership_id", sa.UUID(), nullable=True),
        sa.Column("risk_owner_membership_id", sa.UUID(), nullable=True),
        sa.Column("incident_owner_membership_id", sa.UUID(), nullable=True),
        sa.Column(
            "effective_from",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=True,
        ),
        sa.Column("effective_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", sa.String(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=True,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=True,
        ),
        sa.ForeignKeyConstraint(["ai_system_id"], ["ai_systems.id"]),
        sa.ForeignKeyConstraint(
            ["business_owner_membership_id"], ["organization_memberships.id"]
        ),
        sa.ForeignKeyConstraint(
            ["technical_owner_membership_id"], ["organization_memberships.id"]
        ),
        sa.ForeignKeyConstraint(
            ["rai_officer_membership_id"], ["organization_memberships.id"]
        ),
        sa.ForeignKeyConstraint(
            ["risk_owner_membership_id"], ["organization_memberships.id"]
        ),
        sa.ForeignKeyConstraint(
            ["incident_owner_membership_id"], ["organization_memberships.id"]
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("ai_system_id"),
    )
    op.create_index(
        "ix_ai_system_accountabilities_ai_system_id",
        "ai_system_accountabilities",
        ["ai_system_id"],
    )

    op.create_table(
        "ai_system_governance_classifications",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("ai_system_id", sa.UUID(), nullable=False),
        sa.Column("business_criticality", sa.String(), nullable=True),
        sa.Column("data_sensitivity", sa.String(), nullable=True),
        sa.Column("customer_citizen_impact", sa.String(), nullable=True),
        sa.Column("financial_impact", sa.String(), nullable=True),
        sa.Column("autonomy_level", sa.String(), nullable=True),
        sa.Column("external_facing", sa.Boolean(), nullable=False),
        sa.Column("consequential_actions", sa.Boolean(), nullable=False),
        sa.Column("personal_data", sa.Boolean(), nullable=False),
        sa.Column("regulated_process", sa.Boolean(), nullable=False),
        sa.Column("human_oversight_requirement", sa.String(), nullable=True),
        sa.Column("production", sa.Boolean(), nullable=False),
        sa.Column("updated_by", sa.String(), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=True,
        ),
        sa.ForeignKeyConstraint(["ai_system_id"], ["ai_systems.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("ai_system_id"),
    )
    op.create_index(
        "ix_ai_system_governance_classifications_ai_system_id",
        "ai_system_governance_classifications",
        ["ai_system_id"],
    )

    op.create_table(
        "control_assessments",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("ai_system_id", sa.UUID(), nullable=False),
        sa.Column("agent_version_id", sa.UUID(), nullable=True),
        sa.Column("control_requirement_id", sa.UUID(), nullable=False),
        sa.Column("applicability", sa.String(), nullable=False),
        sa.Column("applicability_reason", sa.Text(), nullable=True),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("assessment_method", sa.String(), nullable=False),
        sa.Column("evidence_refs", sa.JSON(), nullable=True),
        sa.Column("assessed_by", sa.String(), nullable=True),
        sa.Column("assessed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("valid_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=True,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=True,
        ),
        sa.ForeignKeyConstraint(["ai_system_id"], ["ai_systems.id"]),
        sa.ForeignKeyConstraint(["agent_version_id"], ["agent_versions.id"]),
        sa.ForeignKeyConstraint(
            ["control_requirement_id"], ["control_requirements.id"]
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "ai_system_id",
            "control_requirement_id",
            "agent_version_id",
            name="uq_control_assessment_scope",
        ),
    )
    op.create_index(
        "ix_control_assessments_ai_system_id", "control_assessments", ["ai_system_id"]
    )
    op.create_index(
        "ix_control_assessments_agent_version_id",
        "control_assessments",
        ["agent_version_id"],
    )
    op.create_index(
        "ix_control_assessments_control_requirement_id",
        "control_assessments",
        ["control_requirement_id"],
    )
    op.create_index("ix_control_assessments_status", "control_assessments", ["status"])

    op.create_table(
        "governance_reviews",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("ai_system_id", sa.UUID(), nullable=False),
        sa.Column("agent_version_id", sa.UUID(), nullable=True),
        sa.Column("review_type", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("requested_by", sa.String(), nullable=False),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("decision", sa.String(), nullable=True),
        sa.Column("decision_reason", sa.Text(), nullable=True),
        sa.Column("conditions", sa.JSON(), nullable=True),
        sa.Column("evidence_snapshot", sa.JSON(), nullable=True),
        sa.Column("checklist", sa.JSON(), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("decided_by", sa.String(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=True,
        ),
        sa.ForeignKeyConstraint(["ai_system_id"], ["ai_systems.id"]),
        sa.ForeignKeyConstraint(["agent_version_id"], ["agent_versions.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_governance_reviews_ai_system_id", "governance_reviews", ["ai_system_id"]
    )
    op.create_index(
        "ix_governance_reviews_agent_version_id",
        "governance_reviews",
        ["agent_version_id"],
    )
    op.create_index(
        "ix_governance_reviews_review_type", "governance_reviews", ["review_type"]
    )
    op.create_index("ix_governance_reviews_status", "governance_reviews", ["status"])

    op.create_table(
        "governance_review_assignments",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("review_id", sa.UUID(), nullable=False),
        sa.Column("membership_id", sa.UUID(), nullable=True),
        sa.Column("reviewer_user_id", sa.String(), nullable=False),
        sa.Column("role", sa.String(), nullable=True),
        sa.Column(
            "assigned_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=True,
        ),
        sa.ForeignKeyConstraint(["review_id"], ["governance_reviews.id"]),
        sa.ForeignKeyConstraint(["membership_id"], ["organization_memberships.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_governance_review_assignments_review_id",
        "governance_review_assignments",
        ["review_id"],
    )
    op.create_index(
        "ix_governance_review_assignments_reviewer_user_id",
        "governance_review_assignments",
        ["reviewer_user_id"],
    )

    op.create_table(
        "governance_attestations",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("ai_system_id", sa.UUID(), nullable=True),
        sa.Column("agent_version_id", sa.UUID(), nullable=True),
        sa.Column("attestation_type", sa.String(), nullable=False),
        sa.Column("statement", sa.Text(), nullable=False),
        sa.Column("scope", sa.JSON(), nullable=True),
        sa.Column("actor", sa.String(), nullable=False),
        sa.Column("actor_role", sa.String(), nullable=True),
        sa.Column("evidence_refs", sa.JSON(), nullable=True),
        sa.Column("valid_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=True,
        ),
        sa.ForeignKeyConstraint(["ai_system_id"], ["ai_systems.id"]),
        sa.ForeignKeyConstraint(["agent_version_id"], ["agent_versions.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_governance_attestations_ai_system_id",
        "governance_attestations",
        ["ai_system_id"],
    )
    op.create_index(
        "ix_governance_attestations_attestation_type",
        "governance_attestations",
        ["attestation_type"],
    )

    op.create_table(
        "governance_exceptions",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("ai_system_id", sa.UUID(), nullable=False),
        sa.Column("agent_version_id", sa.UUID(), nullable=True),
        sa.Column("control_requirement_id", sa.UUID(), nullable=True),
        sa.Column("scope", sa.JSON(), nullable=True),
        sa.Column("business_justification", sa.Text(), nullable=False),
        sa.Column("risk", sa.String(), nullable=True),
        sa.Column("compensating_controls", sa.JSON(), nullable=True),
        sa.Column("evidence_refs", sa.JSON(), nullable=True),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("requester", sa.String(), nullable=False),
        sa.Column("approver", sa.String(), nullable=True),
        sa.Column("decision_reason", sa.Text(), nullable=True),
        sa.Column("valid_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=True,
        ),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["ai_system_id"], ["ai_systems.id"]),
        sa.ForeignKeyConstraint(["agent_version_id"], ["agent_versions.id"]),
        sa.ForeignKeyConstraint(
            ["control_requirement_id"], ["control_requirements.id"]
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_governance_exceptions_ai_system_id",
        "governance_exceptions",
        ["ai_system_id"],
    )
    op.create_index(
        "ix_governance_exceptions_status", "governance_exceptions", ["status"]
    )

    op.create_table(
        "ai_incidents",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("ai_system_id", sa.UUID(), nullable=False),
        sa.Column("agent_version_id", sa.UUID(), nullable=True),
        sa.Column("runtime_identity_id", sa.UUID(), nullable=True),
        sa.Column("trajectory_id", sa.UUID(), nullable=True),
        sa.Column("severity", sa.String(), nullable=False),
        sa.Column("category", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("source", sa.String(), nullable=False),
        sa.Column("source_ref", sa.String(), nullable=True),
        sa.Column(
            "detected_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=True,
        ),
        sa.Column("reported_by", sa.String(), nullable=False),
        sa.Column("incident_manager", sa.String(), nullable=True),
        sa.Column("containment_action", sa.String(), nullable=True),
        sa.Column("containment_ref", sa.JSON(), nullable=True),
        sa.Column("root_cause", sa.Text(), nullable=True),
        sa.Column("corrective_actions_summary", sa.Text(), nullable=True),
        sa.Column("evidence_refs", sa.JSON(), nullable=True),
        sa.Column("external_ticket_ref", sa.String(), nullable=True),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=True,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=True,
        ),
        sa.ForeignKeyConstraint(["ai_system_id"], ["ai_systems.id"]),
        sa.ForeignKeyConstraint(["agent_version_id"], ["agent_versions.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_ai_incidents_ai_system_id", "ai_incidents", ["ai_system_id"])
    op.create_index(
        "ix_ai_incidents_agent_version_id", "ai_incidents", ["agent_version_id"]
    )
    op.create_index(
        "ix_ai_incidents_runtime_identity_id",
        "ai_incidents",
        ["runtime_identity_id"],
    )
    op.create_index("ix_ai_incidents_trajectory_id", "ai_incidents", ["trajectory_id"])
    op.create_index("ix_ai_incidents_severity", "ai_incidents", ["severity"])
    op.create_index("ix_ai_incidents_category", "ai_incidents", ["category"])
    op.create_index("ix_ai_incidents_status", "ai_incidents", ["status"])

    op.create_table(
        "incident_transitions",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("incident_id", sa.UUID(), nullable=False),
        sa.Column("from_status", sa.String(), nullable=True),
        sa.Column("to_status", sa.String(), nullable=False),
        sa.Column("actor", sa.String(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=True,
        ),
        sa.ForeignKeyConstraint(["incident_id"], ["ai_incidents.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_incident_transitions_incident_id",
        "incident_transitions",
        ["incident_id"],
    )

    op.create_table(
        "incident_corrective_actions",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("incident_id", sa.UUID(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("owner", sa.String(), nullable=False),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("evidence", sa.JSON(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=True,
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["incident_id"], ["ai_incidents.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_incident_corrective_actions_incident_id",
        "incident_corrective_actions",
        ["incident_id"],
    )
    op.create_index(
        "ix_incident_corrective_actions_status",
        "incident_corrective_actions",
        ["status"],
    )

    op.create_table(
        "governance_evidence_packages",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("ai_system_id", sa.UUID(), nullable=True),
        sa.Column("agent_id", sa.UUID(), nullable=True),
        sa.Column("agent_version_id", sa.UUID(), nullable=True),
        sa.Column("review_id", sa.UUID(), nullable=True),
        sa.Column("incident_id", sa.UUID(), nullable=True),
        sa.Column("period_start", sa.DateTime(timezone=True), nullable=True),
        sa.Column("period_end", sa.DateTime(timezone=True), nullable=True),
        sa.Column("generated_by", sa.String(), nullable=False),
        sa.Column(
            "generated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=True,
        ),
        sa.Column("manifest", sa.JSON(), nullable=False),
        sa.Column("package_digest", sa.String(), nullable=False),
        sa.Column("report_html", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["ai_system_id"], ["ai_systems.id"]),
        sa.ForeignKeyConstraint(["agent_id"], ["agents.id"]),
        sa.ForeignKeyConstraint(["agent_version_id"], ["agent_versions.id"]),
        sa.ForeignKeyConstraint(["review_id"], ["governance_reviews.id"]),
        sa.ForeignKeyConstraint(["incident_id"], ["ai_incidents.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_governance_evidence_packages_ai_system_id",
        "governance_evidence_packages",
        ["ai_system_id"],
    )
    op.create_index(
        "ix_governance_evidence_packages_package_digest",
        "governance_evidence_packages",
        ["package_digest"],
    )

    op.create_table(
        "periodic_review_schedules",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("ai_system_id", sa.UUID(), nullable=False),
        sa.Column("frequency_days", sa.Integer(), nullable=False),
        sa.Column("next_due_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("created_by", sa.String(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=True,
        ),
        sa.ForeignKeyConstraint(["ai_system_id"], ["ai_systems.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("ai_system_id"),
    )
    op.create_index(
        "ix_periodic_review_schedules_ai_system_id",
        "periodic_review_schedules",
        ["ai_system_id"],
    )

    op.create_table(
        "pilots",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("sponsor", sa.String(), nullable=True),
        sa.Column("start_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("end_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("success_criteria", sa.JSON(), nullable=True),
        sa.Column("readiness_gate_id", sa.UUID(), nullable=True),
        sa.Column("created_by", sa.String(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=True,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=True,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_pilots_status", "pilots", ["status"])

    op.create_table(
        "pilot_ai_systems",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("pilot_id", sa.UUID(), nullable=False),
        sa.Column("ai_system_id", sa.UUID(), nullable=False),
        sa.Column("agent_version_id", sa.UUID(), nullable=True),
        sa.Column(
            "added_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=True,
        ),
        sa.ForeignKeyConstraint(["pilot_id"], ["pilots.id"]),
        sa.ForeignKeyConstraint(["ai_system_id"], ["ai_systems.id"]),
        sa.ForeignKeyConstraint(["agent_version_id"], ["agent_versions.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("pilot_id", "ai_system_id", name="uq_pilot_ai_system"),
    )
    op.create_index("ix_pilot_ai_systems_pilot_id", "pilot_ai_systems", ["pilot_id"])
    op.create_index(
        "ix_pilot_ai_systems_ai_system_id", "pilot_ai_systems", ["ai_system_id"]
    )

    op.create_table(
        "pilot_readiness_evaluations",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("pilot_id", sa.UUID(), nullable=True),
        sa.Column("ai_system_id", sa.UUID(), nullable=True),
        sa.Column("agent_version_id", sa.UUID(), nullable=True),
        sa.Column("decision", sa.String(), nullable=False),
        sa.Column("dimensions", sa.JSON(), nullable=False),
        sa.Column("gaps", sa.JSON(), nullable=True),
        sa.Column("conditions", sa.JSON(), nullable=True),
        sa.Column("evaluated_by", sa.String(), nullable=False),
        sa.Column(
            "evaluated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=True,
        ),
        sa.ForeignKeyConstraint(["pilot_id"], ["pilots.id"]),
        sa.ForeignKeyConstraint(["ai_system_id"], ["ai_systems.id"]),
        sa.ForeignKeyConstraint(["agent_version_id"], ["agent_versions.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_pilot_readiness_evaluations_pilot_id",
        "pilot_readiness_evaluations",
        ["pilot_id"],
    )
    op.create_index(
        "ix_pilot_readiness_evaluations_ai_system_id",
        "pilot_readiness_evaluations",
        ["ai_system_id"],
    )
    op.create_index(
        "ix_pilot_readiness_evaluations_decision",
        "pilot_readiness_evaluations",
        ["decision"],
    )


def downgrade() -> None:
    op.drop_table("pilot_readiness_evaluations")
    op.drop_table("pilot_ai_systems")
    op.drop_table("pilots")
    op.drop_table("periodic_review_schedules")
    op.drop_table("governance_evidence_packages")
    op.drop_table("incident_corrective_actions")
    op.drop_table("incident_transitions")
    op.drop_table("ai_incidents")
    op.drop_table("governance_exceptions")
    op.drop_table("governance_attestations")
    op.drop_table("governance_review_assignments")
    op.drop_table("governance_reviews")
    op.drop_table("control_assessments")
    op.drop_table("ai_system_governance_classifications")
    op.drop_table("ai_system_accountabilities")
    op.drop_table("control_mappings")
    op.drop_table("control_requirements")
    op.drop_table("control_objectives")
    op.drop_table("control_frameworks")

    op.drop_table("organization_memberships")
    op.drop_table("organization_governance_profiles")
