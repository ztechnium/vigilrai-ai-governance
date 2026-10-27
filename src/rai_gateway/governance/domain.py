"""Domain types for WP8 governance / pilot operating model."""

from __future__ import annotations

from enum import StrEnum


class OrganizationType(StrEnum):
    GOVERNMENT_AGENCY = "GOVERNMENT_AGENCY"
    STATE_OWNED_ENTITY = "STATE_OWNED_ENTITY"
    REGULATED_ENTERPRISE = "REGULATED_ENTERPRISE"
    PRIVATE_ENTERPRISE = "PRIVATE_ENTERPRISE"
    OTHER = "OTHER"


class PilotOrgStatus(StrEnum):
    PLANNING = "PLANNING"
    CONFIGURING = "CONFIGURING"
    READINESS_REVIEW = "READINESS_REVIEW"
    READY = "READY"
    ACTIVE = "ACTIVE"
    PAUSED = "PAUSED"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"


class MembershipStatus(StrEnum):
    INVITED = "INVITED"
    ACTIVE = "ACTIVE"
    SUSPENDED = "SUSPENDED"
    REVOKED = "REVOKED"


class GovernanceRole(StrEnum):
    ORGANIZATION_ADMIN = "ORGANIZATION_ADMIN"
    AI_SYSTEM_OWNER = "AI_SYSTEM_OWNER"
    BUSINESS_OWNER = "BUSINESS_OWNER"
    RAI_OFFICER = "RAI_OFFICER"
    RISK_COMPLIANCE_REVIEWER = "RISK_COMPLIANCE_REVIEWER"
    BUSINESS_APPROVER = "BUSINESS_APPROVER"
    TECHNICAL_OWNER = "TECHNICAL_OWNER"
    AUDITOR = "AUDITOR"
    INCIDENT_MANAGER = "INCIDENT_MANAGER"


class ControlApplicability(StrEnum):
    REQUIRED = "REQUIRED"
    CONDITIONAL = "CONDITIONAL"
    NOT_APPLICABLE = "NOT_APPLICABLE"
    OPTIONAL = "OPTIONAL"


class ControlAssessmentStatus(StrEnum):
    NOT_ASSESSED = "NOT_ASSESSED"
    SATISFIED = "SATISFIED"
    PARTIALLY_SATISFIED = "PARTIALLY_SATISFIED"
    NOT_SATISFIED = "NOT_SATISFIED"
    NOT_APPLICABLE = "NOT_APPLICABLE"
    EXCEPTION_APPROVED = "EXCEPTION_APPROVED"


class AssessmentMethod(StrEnum):
    AUTOMATED = "AUTOMATED"
    MANUAL = "MANUAL"
    MIXED = "MIXED"


class ReviewType(StrEnum):
    INITIAL = "INITIAL"
    PRE_PRODUCTION = "PRE_PRODUCTION"
    PERIODIC = "PERIODIC"
    MATERIAL_CHANGE = "MATERIAL_CHANGE"
    INCIDENT_DRIVEN = "INCIDENT_DRIVEN"
    EXCEPTION_REVIEW = "EXCEPTION_REVIEW"
    RETIREMENT = "RETIREMENT"


class ReviewStatus(StrEnum):
    DRAFT = "DRAFT"
    REQUESTED = "REQUESTED"
    IN_REVIEW = "IN_REVIEW"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"


class ReviewDecision(StrEnum):
    APPROVE = "APPROVE"
    APPROVE_WITH_CONDITIONS = "APPROVE_WITH_CONDITIONS"
    RETURN_FOR_REMEDIATION = "RETURN_FOR_REMEDIATION"
    SUSPEND = "SUSPEND"
    RETIRE = "RETIRE"


class ExceptionStatus(StrEnum):
    REQUESTED = "REQUESTED"
    UNDER_REVIEW = "UNDER_REVIEW"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"
    REVOKED = "REVOKED"
    CLOSED = "CLOSED"


class IncidentSeverity(StrEnum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class IncidentCategory(StrEnum):
    POLICY_VIOLATION = "POLICY_VIOLATION"
    UNAUTHORIZED_ACTION = "UNAUTHORIZED_ACTION"
    DATA_EXPOSURE = "DATA_EXPOSURE"
    SECURITY = "SECURITY"
    FRAUD = "FRAUD"
    FINANCIAL = "FINANCIAL"
    SAFETY = "SAFETY"
    MODEL_BEHAVIOR = "MODEL_BEHAVIOR"
    TOOL_MISUSE = "TOOL_MISUSE"
    AVAILABILITY = "AVAILABILITY"
    COMPLIANCE = "COMPLIANCE"
    OTHER = "OTHER"


class IncidentStatus(StrEnum):
    OPEN = "OPEN"
    TRIAGED = "TRIAGED"
    CONTAINED = "CONTAINED"
    INVESTIGATING = "INVESTIGATING"
    REMEDIATING = "REMEDIATING"
    RESOLVED = "RESOLVED"
    CLOSED = "CLOSED"


class IncidentSource(StrEnum):
    MANUAL = "MANUAL"
    WP6_RISK_FINDING = "WP6_RISK_FINDING"
    WP6_INTERVENTION = "WP6_INTERVENTION"
    WP4_ENFORCEMENT = "WP4_ENFORCEMENT"
    WP5_EVIDENCE_FINDING = "WP5_EVIDENCE_FINDING"
    EXTERNAL = "EXTERNAL"


class CorrectiveActionStatus(StrEnum):
    OPEN = "OPEN"
    IN_PROGRESS = "IN_PROGRESS"
    DONE = "DONE"
    CANCELLED = "CANCELLED"


class EvidenceAvailability(StrEnum):
    AVAILABLE = "AVAILABLE"
    NOT_AVAILABLE = "NOT_AVAILABLE"
    NOT_APPLICABLE = "NOT_APPLICABLE"
    REDACTED = "REDACTED"


class ReadinessDimensionStatus(StrEnum):
    READY = "READY"
    PARTIAL = "PARTIAL"
    NOT_READY = "NOT_READY"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class PilotReadinessDecision(StrEnum):
    READY = "READY"
    READY_WITH_CONDITIONS = "READY_WITH_CONDITIONS"
    NOT_READY = "NOT_READY"


class AttestationType(StrEnum):
    OWNERSHIP = "OWNERSHIP"
    CONTROL = "CONTROL"
    RISK_ACCEPTANCE = "RISK_ACCEPTANCE"
    PERIODIC_REVIEW = "PERIODIC_REVIEW"


READINESS_DIMENSIONS = (
    "ORGANIZATION",
    "ACCOUNTABILITY",
    "REGISTRY",
    "RISK",
    "POLICY",
    "IDENTITY",
    "APPROVAL",
    "ENFORCEMENT",
    "EVIDENCE",
    "OVERSIGHT",
    "ASSURANCE",
    "INCIDENT_RESPONSE",
    "CONTROL_COVERAGE",
)

# Pilot control pack — product control objectives (not legal certification claims).
PILOT_CONTROL_OBJECTIVES: list[dict[str, str]] = [
    {"code": "GOV-01", "title": "Accountable owner assigned", "category": "GOVERNANCE"},
    {
        "code": "GOV-02",
        "title": "Exact production version approved",
        "category": "GOVERNANCE",
    },
    {"code": "RISK-01", "title": "Risk assessment current", "category": "RISK"},
    {
        "code": "RISK-02",
        "title": "Critical risks resolved or accepted",
        "category": "RISK",
    },
    {
        "code": "ID-01",
        "title": "Runtime identity bound to exact version",
        "category": "IDENTITY",
    },
    {"code": "ID-02", "title": "Runtime credentials managed", "category": "IDENTITY"},
    {
        "code": "ACT-01",
        "title": "Consequential actions policy-controlled",
        "category": "ACTION",
    },
    {
        "code": "ACT-02",
        "title": "Required human approval enforced",
        "category": "ACTION",
    },
    {
        "code": "EVAL-01",
        "title": "Required evaluations completed",
        "category": "EVALUATION",
    },
    {
        "code": "EVAL-02",
        "title": "Deployment gate / assurance valid",
        "category": "EVALUATION",
    },
    {"code": "MON-01", "title": "Runtime monitoring active", "category": "MONITORING"},
    {
        "code": "MON-02",
        "title": "Budgets/limits configured where required",
        "category": "MONITORING",
    },
    {"code": "INC-01", "title": "Incident process established", "category": "INCIDENT"},
    {"code": "EVD-01", "title": "Required evidence retained", "category": "EVIDENCE"},
    {
        "code": "EVD-02",
        "title": "Governance decisions reconstructable",
        "category": "EVIDENCE",
    },
]

# Incompatible role pairs for separation of duties (same membership cannot fill both).
INCOMPATIBLE_ACCOUNTABILITY_PAIRS = (
    ("business_owner_membership_id", "rai_officer_membership_id"),
)
