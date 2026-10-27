"""Database models based on core DDL schema."""

import uuid

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

Base = declarative_base()


class Prompt(Base):
    """Prompts table - master prompt definitions."""

    __tablename__ = "prompts"

    prompt_id = Column(String, primary_key=True)
    name = Column(String, nullable=False)
    domain = Column(String)
    description = Column(Text)
    status = Column(String, nullable=False, default="active")
    owner_system_id = Column(String)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    versions = relationship("PromptVersion", back_populates="prompt")
    allowlist_entries = relationship(
        "PromptAllowlist",
        back_populates="prompt",
        overlaps="allowlist_entries,prompt_version",
    )


class PromptVersion(Base):
    """Prompt versions with governance lifecycle."""

    __tablename__ = "prompt_versions"

    prompt_id = Column(String, ForeignKey("prompts.prompt_id"), primary_key=True)
    version = Column(Integer, primary_key=True)
    status = Column(
        String, nullable=False, default="draft"
    )  # draft|biz_approved|rai_approved|active|retired
    template = Column(Text, nullable=False)
    required_vars_schema = Column(JSON, nullable=False)
    expected_output_schema = Column(JSON)
    model_policy = Column(JSON, nullable=False)
    policy_version = Column(String, nullable=False)
    cache_policy = Column(JSON)
    case_policy = Column(JSON)
    rag_policy = Column(JSON)
    judge_policy = Column(JSON)
    xai_policy = Column(JSON)
    review_prompt_template = Column(Text)
    created_by = Column(String, nullable=False)
    approved_by = Column(String)
    approved_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    prompt = relationship("Prompt", back_populates="versions")
    allowlist_entries = relationship(
        "PromptAllowlist",
        back_populates="prompt_version",
        overlaps="allowlist_entries,prompt",
    )
    rai_rules = relationship("PromptRaiRule", back_populates="prompt_version")


class PromptAllowlist(Base):
    """System/module allowlist for prompt access."""

    __tablename__ = "prompt_allowlist"

    prompt_id = Column(String, ForeignKey("prompts.prompt_id"), primary_key=True)
    version = Column(Integer, primary_key=True)
    system_id = Column(String, primary_key=True)
    module = Column(String, primary_key=True)
    allowed = Column(Boolean, nullable=False, default=True)
    conditions = Column(JSON)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Foreign key constraint
    __table_args__ = (
        ForeignKeyConstraint(
            ["prompt_id", "version"],
            ["prompt_versions.prompt_id", "prompt_versions.version"],
        ),
    )

    # Relationships
    prompt = relationship(
        "Prompt",
        back_populates="allowlist_entries",
        overlaps="allowlist_entries,prompt_version",
    )
    prompt_version = relationship(
        "PromptVersion",
        back_populates="allowlist_entries",
        overlaps="allowlist_entries,prompt",
    )


class RaiRule(Base):
    """RAI rules for policy enforcement."""

    __tablename__ = "rai_rules"

    rule_id = Column(String, primary_key=True)
    name = Column(String, nullable=False)
    type = Column(String, nullable=False)  # input|output|rag|governance
    severity = Column(String, nullable=False)  # low|medium|high|critical
    action = Column(String, nullable=False)  # allow|block|redact|flag|require_review
    jurisdiction = Column(String, default="global")
    detectors = Column(JSON, nullable=False)
    policy_text = Column(Text)
    active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    prompt_bindings = relationship("PromptRaiRule", back_populates="rai_rule")


class PromptRaiRule(Base):
    """Binding between prompts and RAI rules."""

    __tablename__ = "prompt_rai_rules"

    prompt_id = Column(String, primary_key=True)
    version = Column(Integer, primary_key=True)
    rule_id = Column(String, ForeignKey("rai_rules.rule_id"), primary_key=True)
    enabled = Column(Boolean, nullable=False, default=True)
    overrides = Column(JSON)

    # Foreign key constraint
    __table_args__ = (
        ForeignKeyConstraint(
            ["prompt_id", "version"],
            ["prompt_versions.prompt_id", "prompt_versions.version"],
        ),
    )

    # Relationships
    prompt_version = relationship("PromptVersion", back_populates="rai_rules")
    rai_rule = relationship("RaiRule", back_populates="prompt_bindings")


class ExecutionAudit(Base):
    """Metadata-only audit trail for executions."""

    __tablename__ = "executions_audit"

    execution_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    trace_id = Column(String, nullable=False)
    prompt_id = Column(String, nullable=False)
    prompt_version = Column(Integer, nullable=False)
    system_id = Column(String, nullable=False)
    system_user_id = Column(String)
    module = Column(String)
    objective = Column(String)
    input_hash = Column(String, nullable=False)
    output_hash = Column(String)
    decision = Column(String, nullable=False)
    reason_codes = Column(ARRAY(String))
    rule_ids = Column(ARRAY(String))
    policy_version = Column(String, nullable=False)
    guard_version = Column(String, nullable=False)
    llm_model = Column(String)
    cache_hit = Column(Boolean, nullable=False, default=False)
    latency_ms = Column(Integer)
    tokens_in = Column(Integer)
    tokens_out = Column(Integer)
    case_id = Column(UUID(as_uuid=True))
    evidence_ref = Column(String)
    citations_refs = Column(JSON)
    classification_level = Column(String)
    classification_tags = Column(ARRAY(String))
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Foreign key constraint
    __table_args__ = (
        ForeignKeyConstraint(
            ["prompt_id", "prompt_version"],
            ["prompt_versions.prompt_id", "prompt_versions.version"],
        ),
    )


class Case(Base):
    """Cases for human review and resolution."""

    __tablename__ = "cases"

    case_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    execution_id = Column(
        UUID(as_uuid=True), ForeignKey("executions_audit.execution_id"), nullable=False
    )
    status = Column(String, nullable=False, default="open")
    owner = Column(String)
    reason_codes = Column(ARRAY(String))
    actions = Column(JSON)
    resolution = Column(String)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class AdminAudit(Base):
    """Admin action audit trail."""

    __tablename__ = "admin_audit"

    admin_event_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    trace_id = Column(String, nullable=False)
    actor_user_id = Column(String, nullable=False)
    actor_role = Column(String, nullable=False)
    action = Column(String, nullable=False)
    target = Column(JSON)
    auth_strength = Column(String)
    diff_ref = Column(String)
    reason = Column(String)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class ApiKey(Base):
    """API key management."""

    __tablename__ = "api_keys"

    api_key_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    key_hash = Column(String, nullable=False)
    system_id = Column(String, nullable=False)
    scopes = Column(ARRAY(String), nullable=False)
    plan = Column(String)
    status = Column(String, nullable=False, default="active")
    expires_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    revoked_at = Column(DateTime(timezone=True))


class ProviderSetting(Base):
    """Persistent runtime settings for LLM provider configuration."""

    __tablename__ = "provider_settings"

    setting_key = Column(String, primary_key=True)
    setting_value = Column(Text)
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class UserAccount(Base):
    """Human user accounts for SaaS and admin console operations."""

    __tablename__ = "users"

    user_id = Column(String, primary_key=True)
    email = Column(String, nullable=False, unique=True)
    name = Column(String, nullable=False)
    status = Column(String, nullable=False, default="active")
    email_verified_at = Column(DateTime(timezone=True), nullable=True)
    welcome_email_sent_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class RoleDefinition(Base):
    """Role catalog."""

    __tablename__ = "roles"

    role_id = Column(String, primary_key=True)
    name = Column(String, nullable=False)
    description = Column(Text)
    is_system = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class RolePermission(Base):
    """Permission bindings per role."""

    __tablename__ = "role_permissions"

    role_id = Column(String, ForeignKey("roles.role_id"), primary_key=True)
    permission = Column(String, primary_key=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class UserRole(Base):
    """User-to-role assignments."""

    __tablename__ = "user_roles"

    user_id = Column(String, ForeignKey("users.user_id"), primary_key=True)
    role_id = Column(String, ForeignKey("roles.role_id"), primary_key=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class AdminCredential(Base):
    """Email/password credentials mapped to admin users."""

    __tablename__ = "admin_credentials"

    email = Column(String, primary_key=True)
    user_id = Column(String, ForeignKey("users.user_id"), nullable=False)
    password_hash = Column(String, nullable=False)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class PolicyDocument(Base):
    """Policy documents for multi-country compliance."""

    __tablename__ = "policy_documents"

    doc_id = Column(String, primary_key=True)
    country = Column(String, nullable=False)
    authority = Column(String)
    doc_type = Column(String)
    version = Column(String)
    effective_date = Column(DateTime)
    content_ref = Column(String)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class PolicyObligation(Base):
    """Structured policy obligations extracted from documents."""

    __tablename__ = "policy_obligations"

    obligation_id = Column(String, primary_key=True)
    doc_id = Column(String, ForeignKey("policy_documents.doc_id"), nullable=False)
    section_ref = Column(String)
    topic = Column(String)
    scope = Column(String)
    constraint_action = Column(String)
    structured = Column(JSON)
    citations = Column(JSON)
    confidence = Column(Integer)
    status = Column(String, nullable=False, default="draft")
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class RagDomain(Base):
    """RAG domains for retrieval-augmented generation sources."""

    __tablename__ = "rag_domains"

    domain_id = Column(String, primary_key=True)
    name = Column(String, nullable=False)
    description = Column(String)
    country = Column(String)  # Jurisdiction for this domain
    owner_email = Column(String)
    status = Column(String, nullable=False, default="draft")  # draft, active, archived
    approval_required = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


class RagSource(Base):
    """Data sources approved for RAG retrieval."""

    __tablename__ = "rag_sources"

    source_id = Column(String, primary_key=True)
    domain_id = Column(String, ForeignKey("rag_domains.domain_id"), nullable=False)
    source_name = Column(String, nullable=False)
    source_type = Column(String)  # document, database, api, web, etc.
    access_url = Column(String)
    description = Column(String)
    leakage_risk_level = Column(String, default="low")  # low, medium, high
    redaction_rules = Column(JSON)  # PII redaction, filtering rules
    source_metadata = Column(JSON)  # Additional source metadata
    status = Column(
        String, nullable=False, default="draft"
    )  # draft, approved, active, revoked
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    approved_at = Column(DateTime(timezone=True))


class RagPolicy(Base):
    """Approved RAG policies for specific prompt versions."""

    __tablename__ = "rag_policies"

    policy_id = Column(String, primary_key=True)
    prompt_id = Column(String, ForeignKey("prompts.prompt_id"), nullable=False)
    prompt_version = Column(
        Integer, nullable=False
    )  # Reference to PromptVersion but not as FK due to compound key
    domain_id = Column(String, ForeignKey("rag_domains.domain_id"), nullable=False)
    country = Column(String)
    status = Column(String, nullable=False, default="draft")  # draft, approved, active
    proposed_by = Column(String)
    approved_by = Column(String)
    auto_approve_required = Column(Boolean, default=False)
    approval_notes = Column(String)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    approved_at = Column(DateTime(timezone=True))
