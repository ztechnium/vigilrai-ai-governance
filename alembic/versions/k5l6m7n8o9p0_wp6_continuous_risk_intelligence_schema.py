"""wp6_continuous_risk_intelligence_schema

Revision ID: k5l6m7n8o9p0
Revises: j4k5l6m7n8o9
Create Date: 2026-09-09 23:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "k5l6m7n8o9p0"
down_revision: Union[str, None] = "j4k5l6m7n8o9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "content_rules",
        sa.Column("applies_to", sa.String(), nullable=False, server_default="BOTH"),
    )
    op.add_column(
        "content_rules",
        sa.Column("rule_version", sa.Integer(), nullable=False, server_default="1"),
    )
    op.add_column(
        "content_rules",
        sa.Column("category", sa.String(), nullable=True),
    )
    op.add_column(
        "content_rules",
        sa.Column("severity", sa.String(), nullable=True),
    )

    op.create_table(
        "content_evaluator_configs",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("ai_system_id", sa.UUID(), nullable=True),
        sa.Column("provider", sa.String(), nullable=False),
        sa.Column("model", sa.String(), nullable=False),
        sa.Column("temperature", sa.Float(), nullable=False),
        sa.Column("timeout_seconds", sa.Integer(), nullable=False),
        sa.Column("max_rules_per_call", sa.Integer(), nullable=False),
        sa.Column("confidence_threshold", sa.Float(), nullable=False),
        sa.Column("minimum_confidence_to_mark", sa.Float(), nullable=False),
        sa.Column("minimum_confidence_to_monitor", sa.Float(), nullable=False),
        sa.Column("minimum_confidence_to_intervene", sa.Float(), nullable=False),
        sa.Column("fail_closed", sa.Boolean(), nullable=False),
        sa.Column("fallback_provider", sa.String(), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("api_key_encrypted", sa.Text(), nullable=True),
        sa.Column("health_status", sa.String(), nullable=False),
        sa.Column("last_success_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("latency_ms_avg", sa.Float(), nullable=True),
        sa.Column("error_rate", sa.Float(), nullable=True),
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
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "ai_system_id", name="uq_content_evaluator_config_ai_system"
        ),
    )
    op.create_index(
        op.f("ix_content_evaluator_configs_ai_system_id"),
        "content_evaluator_configs",
        ["ai_system_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_content_evaluator_configs_enabled"),
        "content_evaluator_configs",
        ["enabled"],
        unique=False,
    )

    op.create_table(
        "risk_signals",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("trajectory_id", sa.UUID(), nullable=True),
        sa.Column("ai_system_id", sa.UUID(), nullable=False),
        sa.Column("agent_id", sa.UUID(), nullable=True),
        sa.Column("agent_version_id", sa.UUID(), nullable=True),
        sa.Column("runtime_identity_id", sa.UUID(), nullable=True),
        sa.Column("signal_type", sa.String(), nullable=False),
        sa.Column("source_event_id", sa.UUID(), nullable=True),
        sa.Column("source_type", sa.String(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("severity", sa.String(), nullable=False),
        sa.Column("sensitivity", sa.String(), nullable=False),
        sa.Column("dimensions", sa.JSON(), nullable=True),
        sa.Column("evidence_refs", sa.JSON(), nullable=True),
        sa.Column("category", sa.String(), nullable=True),
        sa.Column("payload", sa.JSON(), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=True,
        ),
        sa.ForeignKeyConstraint(["agent_id"], ["agents.id"]),
        sa.ForeignKeyConstraint(["agent_version_id"], ["agent_versions.id"]),
        sa.ForeignKeyConstraint(["ai_system_id"], ["ai_systems.id"]),
        sa.ForeignKeyConstraint(
            ["runtime_identity_id"], ["agent_runtime_identities.id"]
        ),
        sa.ForeignKeyConstraint(["trajectory_id"], ["runtime_trajectories.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_risk_signals_ai_system_id"), "risk_signals", ["ai_system_id"]
    )
    op.create_index(
        op.f("ix_risk_signals_trajectory_id"), "risk_signals", ["trajectory_id"]
    )
    op.create_index(
        op.f("ix_risk_signals_runtime_identity_id"),
        "risk_signals",
        ["runtime_identity_id"],
    )
    op.create_index(
        op.f("ix_risk_signals_signal_type"), "risk_signals", ["signal_type"]
    )
    op.create_index(op.f("ix_risk_signals_severity"), "risk_signals", ["severity"])
    op.create_index(op.f("ix_risk_signals_category"), "risk_signals", ["category"])
    op.create_index(
        op.f("ix_risk_signals_occurred_at"), "risk_signals", ["occurred_at"]
    )

    op.create_table(
        "risk_states",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("ai_system_id", sa.UUID(), nullable=False),
        sa.Column("scope_type", sa.String(), nullable=False),
        sa.Column("scope_id", sa.String(), nullable=False),
        sa.Column("current_level", sa.String(), nullable=False),
        sa.Column("cumulative_score", sa.Integer(), nullable=False),
        sa.Column("signal_count", sa.Integer(), nullable=False),
        sa.Column("high_severity_count", sa.Integer(), nullable=False),
        sa.Column("score_breakdown", sa.JSON(), nullable=True),
        sa.Column("dimensions", sa.JSON(), nullable=True),
        sa.Column("last_signal_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("monitoring_status", sa.String(), nullable=False),
        sa.Column("require_approval", sa.Boolean(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=True,
        ),
        sa.ForeignKeyConstraint(["ai_system_id"], ["ai_systems.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("scope_type", "scope_id", name="uq_risk_state_scope"),
    )
    op.create_index(
        op.f("ix_risk_states_ai_system_id"), "risk_states", ["ai_system_id"]
    )
    op.create_index(op.f("ix_risk_states_scope_type"), "risk_states", ["scope_type"])
    op.create_index(op.f("ix_risk_states_scope_id"), "risk_states", ["scope_id"])
    op.create_index(
        op.f("ix_risk_states_current_level"), "risk_states", ["current_level"]
    )

    op.create_table(
        "runtime_risk_findings",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("trajectory_id", sa.UUID(), nullable=True),
        sa.Column("ai_system_id", sa.UUID(), nullable=False),
        sa.Column("agent_id", sa.UUID(), nullable=True),
        sa.Column("agent_version_id", sa.UUID(), nullable=True),
        sa.Column("runtime_identity_id", sa.UUID(), nullable=True),
        sa.Column("finding_type", sa.String(), nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("severity", sa.String(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("sensitivity", sa.String(), nullable=False),
        sa.Column("category", sa.String(), nullable=True),
        sa.Column("dimensions", sa.JSON(), nullable=True),
        sa.Column("signal_ids", sa.JSON(), nullable=True),
        sa.Column("evidence_refs", sa.JSON(), nullable=True),
        sa.Column("policy_rule_ids", sa.JSON(), nullable=True),
        sa.Column("intervention_effect", sa.String(), nullable=True),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("explanation", sa.JSON(), nullable=True),
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
        sa.ForeignKeyConstraint(["agent_id"], ["agents.id"]),
        sa.ForeignKeyConstraint(["agent_version_id"], ["agent_versions.id"]),
        sa.ForeignKeyConstraint(["ai_system_id"], ["ai_systems.id"]),
        sa.ForeignKeyConstraint(
            ["runtime_identity_id"], ["agent_runtime_identities.id"]
        ),
        sa.ForeignKeyConstraint(["trajectory_id"], ["runtime_trajectories.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_runtime_risk_findings_ai_system_id"),
        "runtime_risk_findings",
        ["ai_system_id"],
    )
    op.create_index(
        op.f("ix_runtime_risk_findings_trajectory_id"),
        "runtime_risk_findings",
        ["trajectory_id"],
    )
    op.create_index(
        op.f("ix_runtime_risk_findings_runtime_identity_id"),
        "runtime_risk_findings",
        ["runtime_identity_id"],
    )
    op.create_index(
        op.f("ix_runtime_risk_findings_finding_type"),
        "runtime_risk_findings",
        ["finding_type"],
    )
    op.create_index(
        op.f("ix_runtime_risk_findings_severity"),
        "runtime_risk_findings",
        ["severity"],
    )
    op.create_index(
        op.f("ix_runtime_risk_findings_category"),
        "runtime_risk_findings",
        ["category"],
    )
    op.create_index(
        op.f("ix_runtime_risk_findings_status"),
        "runtime_risk_findings",
        ["status"],
    )

    op.create_table(
        "risk_monitor_rules",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("ai_system_id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("scope", sa.String(), nullable=False),
        sa.Column("signal_type", sa.String(), nullable=True),
        sa.Column("tool_id", sa.UUID(), nullable=True),
        sa.Column("tool_name", sa.String(), nullable=True),
        sa.Column("window_seconds", sa.Integer(), nullable=False),
        sa.Column("aggregation", sa.String(), nullable=False),
        sa.Column("threshold", sa.Float(), nullable=False),
        sa.Column("amount_parameter_path", sa.String(), nullable=True),
        sa.Column("effect", sa.String(), nullable=False),
        sa.Column("monitor_duration_seconds", sa.Integer(), nullable=True),
        sa.Column("monitor_action_count", sa.Integer(), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False),
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
        sa.ForeignKeyConstraint(["tool_id"], ["tool_resources.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_risk_monitor_rules_ai_system_id"),
        "risk_monitor_rules",
        ["ai_system_id"],
    )
    op.create_index(
        op.f("ix_risk_monitor_rules_enabled"),
        "risk_monitor_rules",
        ["enabled"],
    )

    op.create_table(
        "risk_monitors",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("ai_system_id", sa.UUID(), nullable=False),
        sa.Column("monitor_rule_id", sa.UUID(), nullable=True),
        sa.Column("scope_type", sa.String(), nullable=False),
        sa.Column("scope_id", sa.String(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("current_count", sa.Integer(), nullable=False),
        sa.Column("current_sum", sa.Float(), nullable=False),
        sa.Column("threshold", sa.Float(), nullable=True),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=True,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finding_id", sa.UUID(), nullable=True),
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
        sa.ForeignKeyConstraint(["monitor_rule_id"], ["risk_monitor_rules.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_risk_monitors_ai_system_id"), "risk_monitors", ["ai_system_id"]
    )
    op.create_index(
        op.f("ix_risk_monitors_scope_type"), "risk_monitors", ["scope_type"]
    )
    op.create_index(op.f("ix_risk_monitors_scope_id"), "risk_monitors", ["scope_id"])
    op.create_index(op.f("ix_risk_monitors_status"), "risk_monitors", ["status"])
    op.create_index(
        op.f("ix_risk_monitors_expires_at"), "risk_monitors", ["expires_at"]
    )

    op.create_table(
        "runtime_constraints",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("ai_system_id", sa.UUID(), nullable=False),
        sa.Column("scope_type", sa.String(), nullable=False),
        sa.Column("scope_id", sa.String(), nullable=False),
        sa.Column("resource_type", sa.String(), nullable=True),
        sa.Column("resource_id", sa.String(), nullable=True),
        sa.Column("constraint_type", sa.String(), nullable=False),
        sa.Column("value", sa.JSON(), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column(
            "starts_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=True,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("intervention_id", sa.UUID(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=True,
        ),
        sa.ForeignKeyConstraint(["ai_system_id"], ["ai_systems.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_runtime_constraints_ai_system_id"),
        "runtime_constraints",
        ["ai_system_id"],
    )
    op.create_index(
        op.f("ix_runtime_constraints_scope_type"),
        "runtime_constraints",
        ["scope_type"],
    )
    op.create_index(
        op.f("ix_runtime_constraints_scope_id"),
        "runtime_constraints",
        ["scope_id"],
    )
    op.create_index(
        op.f("ix_runtime_constraints_status"),
        "runtime_constraints",
        ["status"],
    )
    op.create_index(
        op.f("ix_runtime_constraints_expires_at"),
        "runtime_constraints",
        ["expires_at"],
    )

    op.create_table(
        "intervention_decisions",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("trajectory_id", sa.UUID(), nullable=True),
        sa.Column("ai_system_id", sa.UUID(), nullable=False),
        sa.Column("scope_type", sa.String(), nullable=False),
        sa.Column("scope_id", sa.String(), nullable=False),
        sa.Column("effect", sa.String(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("risk_level", sa.String(), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("triggering_signal_ids", sa.JSON(), nullable=True),
        sa.Column("policy_rule_ids", sa.JSON(), nullable=True),
        sa.Column("finding_id", sa.UUID(), nullable=True),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("authorization_mode", sa.String(), nullable=True),
        sa.Column("automatic", sa.Boolean(), nullable=False),
        sa.Column("explanation", sa.JSON(), nullable=True),
        sa.Column("executed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("executed_by", sa.String(), nullable=True),
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
        sa.ForeignKeyConstraint(["trajectory_id"], ["runtime_trajectories.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_intervention_decisions_ai_system_id"),
        "intervention_decisions",
        ["ai_system_id"],
    )
    op.create_index(
        op.f("ix_intervention_decisions_trajectory_id"),
        "intervention_decisions",
        ["trajectory_id"],
    )
    op.create_index(
        op.f("ix_intervention_decisions_scope_id"),
        "intervention_decisions",
        ["scope_id"],
    )
    op.create_index(
        op.f("ix_intervention_decisions_effect"),
        "intervention_decisions",
        ["effect"],
    )
    op.create_index(
        op.f("ix_intervention_decisions_status"),
        "intervention_decisions",
        ["status"],
    )

    op.create_table(
        "policy_recommendations",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("ai_system_id", sa.UUID(), nullable=False),
        sa.Column("recommendation_type", sa.String(), nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=True),
        sa.Column("evidence_refs", sa.JSON(), nullable=True),
        sa.Column("proposed_rule", sa.JSON(), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("pattern_key", sa.String(), nullable=True),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("draft_rule_id", sa.UUID(), nullable=True),
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
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_policy_recommendations_ai_system_id"),
        "policy_recommendations",
        ["ai_system_id"],
    )
    op.create_index(
        op.f("ix_policy_recommendations_recommendation_type"),
        "policy_recommendations",
        ["recommendation_type"],
    )
    op.create_index(
        op.f("ix_policy_recommendations_pattern_key"),
        "policy_recommendations",
        ["pattern_key"],
    )
    op.create_index(
        op.f("ix_policy_recommendations_status"),
        "policy_recommendations",
        ["status"],
    )

    op.create_table(
        "content_evaluation_results",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("ai_system_id", sa.UUID(), nullable=False),
        sa.Column("trajectory_id", sa.UUID(), nullable=True),
        sa.Column("content_type", sa.String(), nullable=False),
        sa.Column("evaluation_mode", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("failure_type", sa.String(), nullable=True),
        sa.Column("provider", sa.String(), nullable=True),
        sa.Column("model", sa.String(), nullable=True),
        sa.Column("content_digest", sa.String(), nullable=False),
        sa.Column("rule_set_digest", sa.String(), nullable=False),
        sa.Column("cache_key", sa.String(), nullable=False),
        sa.Column("evaluations", sa.JSON(), nullable=True),
        sa.Column("rule_ids", sa.JSON(), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=True,
        ),
        sa.ForeignKeyConstraint(["ai_system_id"], ["ai_systems.id"]),
        sa.ForeignKeyConstraint(["trajectory_id"], ["runtime_trajectories.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("cache_key", name="uq_content_evaluation_cache_key"),
    )
    op.create_index(
        op.f("ix_content_evaluation_results_ai_system_id"),
        "content_evaluation_results",
        ["ai_system_id"],
    )
    op.create_index(
        op.f("ix_content_evaluation_results_trajectory_id"),
        "content_evaluation_results",
        ["trajectory_id"],
    )
    op.create_index(
        op.f("ix_content_evaluation_results_status"),
        "content_evaluation_results",
        ["status"],
    )
    op.create_index(
        op.f("ix_content_evaluation_results_content_digest"),
        "content_evaluation_results",
        ["content_digest"],
    )


def downgrade() -> None:
    op.drop_table("content_evaluation_results")
    op.drop_table("policy_recommendations")
    op.drop_table("intervention_decisions")
    op.drop_table("runtime_constraints")
    op.drop_table("risk_monitors")
    op.drop_table("risk_monitor_rules")
    op.drop_table("runtime_risk_findings")
    op.drop_table("risk_states")
    op.drop_table("risk_signals")
    op.drop_table("content_evaluator_configs")
    op.drop_column("content_rules", "severity")
    op.drop_column("content_rules", "category")
    op.drop_column("content_rules", "rule_version")
    op.drop_column("content_rules", "applies_to")
