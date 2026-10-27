"""Domain types for WP9 portfolio transparency & executive oversight."""

from __future__ import annotations

from enum import StrEnum


class Freshness(StrEnum):
    LIVE = "LIVE"
    NEAR_REAL_TIME = "NEAR_REAL_TIME"
    SNAPSHOT = "SNAPSHOT"


class ReportScopeType(StrEnum):
    ORGANIZATION = "ORGANIZATION"
    BUSINESS_UNIT = "BUSINESS_UNIT"
    AI_SYSTEM = "AI_SYSTEM"


class ReportCadence(StrEnum):
    WEEKLY = "WEEKLY"
    MONTHLY = "MONTHLY"
    QUARTERLY = "QUARTERLY"


class ExecutiveDecision(StrEnum):
    CONTINUE = "CONTINUE"
    CONSTRAIN = "CONSTRAIN"
    SUSPEND = "SUSPEND"
    PRIORITIZE_REMEDIATION = "PRIORITIZE_REMEDIATION"
    REQUIRE_REASSESSMENT = "REQUIRE_REASSESSMENT"
    RETIRE = "RETIRE"


class AttentionType(StrEnum):
    CRITICAL_RISK_FINDING = "CRITICAL_RISK_FINDING"
    EXPIRED_PRODUCTION_ASSURANCE = "EXPIRED_PRODUCTION_ASSURANCE"
    FAILED_DEPLOYMENT_GATE = "FAILED_DEPLOYMENT_GATE"
    OPEN_CRITICAL_INCIDENT = "OPEN_CRITICAL_INCIDENT"
    OVERDUE_GOVERNANCE_REVIEW = "OVERDUE_GOVERNANCE_REVIEW"
    EXPIRING_WAIVER = "EXPIRING_WAIVER"
    EXPIRING_EXCEPTION = "EXPIRING_EXCEPTION"
    SUSPENDED_RUNTIME_IDENTITY = "SUSPENDED_RUNTIME_IDENTITY"
    PILOT_NOT_READY = "PILOT_NOT_READY"
    MISSING_REQUIRED_OWNER = "MISSING_REQUIRED_OWNER"
    PERSISTENT_EVIDENCE_GAP = "PERSISTENT_EVIDENCE_GAP"
    REPEATED_HIGH_RISK_ANOMALY = "REPEATED_HIGH_RISK_ANOMALY"
    ASSURANCE_EXPIRING = "ASSURANCE_EXPIRING"
    CONTROL_GAP = "CONTROL_GAP"


class AttentionSeverity(StrEnum):
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    INFO = "INFO"


ATTENTION_ACTIONS: dict[AttentionType, str] = {
    AttentionType.CRITICAL_RISK_FINDING: "Resolve critical finding",
    AttentionType.EXPIRED_PRODUCTION_ASSURANCE: "Re-run required evaluation",
    AttentionType.FAILED_DEPLOYMENT_GATE: "Re-run required evaluation",
    AttentionType.OPEN_CRITICAL_INCIDENT: "Review critical incident",
    AttentionType.OVERDUE_GOVERNANCE_REVIEW: "Complete overdue governance review",
    AttentionType.EXPIRING_WAIVER: "Renew or close waiver",
    AttentionType.EXPIRING_EXCEPTION: "Renew/close exception",
    AttentionType.SUSPENDED_RUNTIME_IDENTITY: "Reactivate or retire suspended runtime",
    AttentionType.PILOT_NOT_READY: "Close pilot readiness gaps",
    AttentionType.MISSING_REQUIRED_OWNER: "Assign Business Owner",
    AttentionType.PERSISTENT_EVIDENCE_GAP: "Remediate evidence completeness",
    AttentionType.REPEATED_HIGH_RISK_ANOMALY: "Investigate repeated high-risk anomaly",
    AttentionType.ASSURANCE_EXPIRING: "Renew assurance before expiry",
    AttentionType.CONTROL_GAP: "Remediate control gap",
}

SCHEMA_VERSION = "1.0"
