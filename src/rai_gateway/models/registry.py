"""SQLAlchemy models for WP1 AI system/agent registry."""

from __future__ import annotations

import uuid

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from rai_gateway.models.database import Base


class AISystem(Base):
    __tablename__ = "ai_systems"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    system_key = Column(String, nullable=False, unique=True, index=True)
    name = Column(String, nullable=False)
    description = Column(Text)
    business_purpose = Column(Text)
    business_unit = Column(String)
    owner_id = Column(String)
    technical_owner_id = Column(String)
    status = Column(String, nullable=False, default="DRAFT")
    criticality = Column(String)
    risk_tier = Column(String)
    data_classification = Column(String)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    created_by = Column(String, nullable=False)
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    updated_by = Column(String)
    retired_at = Column(DateTime(timezone=True))

    agents = relationship("Agent", back_populates="ai_system")


class Agent(Base):
    __tablename__ = "agents"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    agent_key = Column(String, nullable=False, unique=True, index=True)
    ai_system_id = Column(
        UUID(as_uuid=True), ForeignKey("ai_systems.id"), nullable=False, index=True
    )
    name = Column(String, nullable=False)
    description = Column(Text)
    business_purpose = Column(Text)
    owner_id = Column(String)
    avatar = Column(Text, nullable=True)
    status = Column(String, nullable=False, default="DRAFT")
    current_version_id = Column(
        UUID(as_uuid=True), ForeignKey("agent_versions.id", use_alter=True)
    )
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    created_by = Column(String, nullable=False)
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    updated_by = Column(String)
    retired_at = Column(DateTime(timezone=True))

    ai_system = relationship("AISystem", back_populates="agents")
    versions = relationship(
        "AgentVersion",
        back_populates="agent",
        foreign_keys="AgentVersion.agent_id",
    )
    current_version = relationship(
        "AgentVersion",
        foreign_keys=[current_version_id],
        post_update=True,
    )


class AgentVersion(Base):
    __tablename__ = "agent_versions"
    __table_args__ = (
        UniqueConstraint("agent_id", "version_number", name="uq_agent_version_number"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    agent_id = Column(
        UUID(as_uuid=True), ForeignKey("agents.id"), nullable=False, index=True
    )
    version_number = Column(Integer, nullable=False)
    change_summary = Column(Text)
    lifecycle_status = Column(String, nullable=False, default="DRAFT")
    configuration_snapshot = Column(JSON)
    configuration_digest = Column(String)
    # Controlled test instance for WP7 live evaluation of this exact version.
    evaluation_endpoint_url = Column(String, nullable=True)
    risk_tier = Column(String)
    material_change_status = Column(String, nullable=False, default="NONE")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    created_by = Column(String, nullable=False)
    submitted_at = Column(DateTime(timezone=True))
    approved_at = Column(DateTime(timezone=True))
    retired_at = Column(DateTime(timezone=True))

    agent = relationship(
        "Agent",
        back_populates="versions",
        foreign_keys=[agent_id],
    )
    dependencies = relationship(
        "AgentVersionDependency", back_populates="agent_version"
    )
    risk_assessments = relationship("RiskAssessment", back_populates="agent_version")


class ModelResource(Base):
    __tablename__ = "model_resources"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    scope = Column(String, nullable=False, default="PLATFORM", index=True)
    provider = Column(String, nullable=False)
    model_name = Column(String, nullable=False)
    model_version = Column(String)
    deployment_reference = Column(String)
    hosting_type = Column(String)
    status = Column(String, nullable=False, default="ACTIVE")
    metadata_ = Column("metadata", JSON)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class ToolResource(Base):
    __tablename__ = "tool_resources"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    scope = Column(String, nullable=False, default="PLATFORM", index=True)
    tool_key = Column(String, nullable=False, index=True)
    name = Column(String, nullable=False)
    description = Column(Text)
    category = Column(String)
    provider = Column(String)
    mcp_server_id = Column(
        UUID(as_uuid=True), ForeignKey("mcp_servers.id"), nullable=True, index=True
    )
    sensitivity = Column(String)
    consequential_action = Column(Boolean, nullable=False, default=False)
    status = Column(String, nullable=False, default="ACTIVE")
    metadata_ = Column("metadata", JSON)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    mcp_server = relationship("MCPServer", back_populates="tools")


class MCPServer(Base):
    __tablename__ = "mcp_servers"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    scope = Column(String, nullable=False, default="PLATFORM", index=True)
    server_key = Column(String, nullable=False, index=True)
    name = Column(String, nullable=False)
    description = Column(Text)
    provider = Column(String)
    environment = Column(String)
    endpoint_reference = Column(String)
    trust_classification = Column(String)
    status = Column(String, nullable=False, default="ACTIVE")
    metadata_ = Column("metadata", JSON)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    tools = relationship("ToolResource", back_populates="mcp_server")


class ExternalService(Base):
    __tablename__ = "external_services"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    scope = Column(String, nullable=False, default="PLATFORM", index=True)
    service_key = Column(String, nullable=False, index=True)
    name = Column(String, nullable=False)
    description = Column(Text)
    provider = Column(String)
    environment = Column(String)
    endpoint_reference = Column(String)
    sensitivity = Column(String)
    trust_classification = Column(String)
    status = Column(String, nullable=False, default="ACTIVE")
    metadata_ = Column("metadata", JSON)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class DataSource(Base):
    __tablename__ = "data_sources"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    scope = Column(String, nullable=False, default="PLATFORM", index=True)
    data_source_key = Column(String, nullable=False, index=True)
    name = Column(String, nullable=False)
    description = Column(Text)
    owner = Column(String)
    classification = Column(String)
    contains_personal_data = Column(Boolean, nullable=False, default=False)
    contains_sensitive_data = Column(Boolean, nullable=False, default=False)
    jurisdiction = Column(String)
    status = Column(String, nullable=False, default="ACTIVE")
    metadata_ = Column("metadata", JSON)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class AgentVersionDependency(Base):
    __tablename__ = "agent_version_dependencies"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    agent_version_id = Column(
        UUID(as_uuid=True), ForeignKey("agent_versions.id"), nullable=False, index=True
    )
    resource_type = Column(String, nullable=False)
    resource_id = Column(UUID(as_uuid=True), nullable=False)
    usage_purpose = Column(String)
    access_mode = Column(String)
    capability_declaration = Column(String)
    required = Column(Boolean, nullable=False, default=True)
    metadata_ = Column("metadata", JSON)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    agent_version = relationship("AgentVersion", back_populates="dependencies")


class RiskAssessment(Base):
    __tablename__ = "risk_assessments"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    ai_system_id = Column(
        UUID(as_uuid=True), ForeignKey("ai_systems.id"), nullable=False, index=True
    )
    agent_version_id = Column(
        UUID(as_uuid=True), ForeignKey("agent_versions.id"), index=True
    )
    assessment_version = Column(Integer, nullable=False, default=1)
    status = Column(String, nullable=False, default="DRAFT")
    overall_score = Column(Integer)
    risk_tier = Column(String)
    impact_score = Column(Integer)
    likelihood_score = Column(Integer)
    exposure_score = Column(Integer)
    confidence_score = Column(Integer)
    rationale = Column(Text)
    assessed_by = Column(String)
    assessed_at = Column(DateTime(timezone=True))
    next_review_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    agent_version = relationship("AgentVersion", back_populates="risk_assessments")
    findings = relationship("RiskFinding", back_populates="risk_assessment")


class RiskFinding(Base):
    __tablename__ = "risk_findings"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    risk_assessment_id = Column(
        UUID(as_uuid=True),
        ForeignKey("risk_assessments.id"),
        nullable=False,
        index=True,
    )
    category = Column(String, nullable=False)
    title = Column(String, nullable=False)
    description = Column(Text)
    severity = Column(String, nullable=False)
    likelihood = Column(Integer)
    impact = Column(Integer)
    score = Column(Integer)
    source = Column(String)
    rationale = Column(Text)
    status = Column(String, nullable=False, default="OPEN")
    owner = Column(String)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    risk_assessment = relationship("RiskAssessment", back_populates="findings")
    enterprise_risk_links = relationship(
        "RiskFindingEnterpriseRiskLink", back_populates="risk_finding"
    )


class EnterpriseRiskReference(Base):
    __tablename__ = "enterprise_risk_references"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    external_key = Column(String, nullable=False, unique=True, index=True)
    source_system = Column(String, nullable=False)
    name = Column(String, nullable=False)
    description = Column(Text)
    category = Column(String)
    metadata_ = Column("metadata", JSON)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class RiskFindingEnterpriseRiskLink(Base):
    __tablename__ = "risk_finding_enterprise_risk_links"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    risk_finding_id = Column(
        UUID(as_uuid=True), ForeignKey("risk_findings.id"), nullable=False, index=True
    )
    enterprise_risk_reference_id = Column(
        UUID(as_uuid=True),
        ForeignKey("enterprise_risk_references.id"),
        nullable=False,
        index=True,
    )
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    risk_finding = relationship("RiskFinding", back_populates="enterprise_risk_links")
    enterprise_risk_reference = relationship("EnterpriseRiskReference")


class MaterialChangeRecord(Base):
    __tablename__ = "material_change_records"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    from_version_id = Column(UUID(as_uuid=True), ForeignKey("agent_versions.id"))
    to_version_id = Column(
        UUID(as_uuid=True), ForeignKey("agent_versions.id"), nullable=False, index=True
    )
    change_category = Column(String, nullable=False)
    change_description = Column(String, nullable=False)
    is_material = Column(Boolean, nullable=False, default=False)
    reason = Column(Text)
    previous_value = Column(String)
    current_value = Column(String)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
