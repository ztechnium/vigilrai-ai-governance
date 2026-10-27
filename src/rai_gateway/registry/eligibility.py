"""Central governance eligibility service."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy.orm import Session

from rai_gateway.models.registry import Agent, AgentVersion, AISystem
from rai_gateway.registry.domain import (
    GOVERNANCE_ELIGIBLE_AGENT_STATUSES,
    GOVERNANCE_ELIGIBLE_SYSTEM_STATUSES,
    GOVERNANCE_ELIGIBLE_VERSION_STATUSES,
    AgentVersionStatus,
    MaterialChangeStatus,
)


@dataclass
class EligibilityResult:
    eligible: bool
    reason: str
    system_id: UUID | None = None
    agent_id: UUID | None = None
    version_id: UUID | None = None


class EligibilityService:
    """Server-authoritative governance eligibility evaluation."""

    def __init__(self, db: Session) -> None:
        self._db = db

    def evaluate(
        self,
        *,
        system_id: UUID | str | None = None,
        system_key: str | None = None,
        agent_id: UUID | str | None = None,
        agent_key: str | None = None,
        version_id: UUID | str | None = None,
        version_number: int | None = None,
        caller_system_id: str | None = None,
        caller_tools: list[str] | None = None,
        environment: str | None = "PRODUCTION",
        skip_assurance: bool = False,
    ) -> EligibilityResult:
        """Evaluate governance eligibility from authoritative persisted state.

        When required WP7 evaluation requirements exist for ``environment``,
        a VALID/CONDITIONAL assurance record is mandatory. Runtime (WP2/WP4)
        callers omit ``skip_assurance`` and default to PRODUCTION.
        """
        system = self._resolve_system(system_id, system_key)
        if system is None:
            return EligibilityResult(False, "AI system not found")

        if caller_system_id and str(system.id) != caller_system_id:
            if system.system_key != caller_system_id:
                return EligibilityResult(
                    False,
                    "Agent does not belong to claimed system",
                    system_id=system.id,
                )

        agent = self._resolve_agent(agent_id, agent_key, system)
        if agent is None:
            return EligibilityResult(
                False,
                "Agent not found or does not belong to system",
                system_id=system.id,
            )

        version = self._resolve_version(agent, version_id, version_number)
        if version is None:
            return EligibilityResult(
                False,
                "Agent version not found",
                system_id=system.id,
                agent_id=agent.id,
            )

        # System lifecycle
        try:
            system_status = system.status
        except Exception:
            return EligibilityResult(
                False, "Invalid system status", system_id=system.id
            )

        if system_status not in {s.value for s in GOVERNANCE_ELIGIBLE_SYSTEM_STATUSES}:
            return EligibilityResult(
                False,
                f"AI system status {system_status} is not governance-eligible",
                system_id=system.id,
                agent_id=agent.id,
                version_id=version.id,
            )

        # Agent lifecycle
        if agent.status not in {s.value for s in GOVERNANCE_ELIGIBLE_AGENT_STATUSES}:
            return EligibilityResult(
                False,
                f"Agent status {agent.status} is not governance-eligible",
                system_id=system.id,
                agent_id=agent.id,
                version_id=version.id,
            )

        # Version lifecycle
        if version.lifecycle_status not in {
            s.value for s in GOVERNANCE_ELIGIBLE_VERSION_STATUSES
        }:
            return EligibilityResult(
                False,
                f"Version status {version.lifecycle_status} is not governance-eligible",
                system_id=system.id,
                agent_id=agent.id,
                version_id=version.id,
            )

        # Material change blocks unapproved versions
        if version.material_change_status == MaterialChangeStatus.MATERIAL.value:
            if version.lifecycle_status != AgentVersionStatus.APPROVED.value:
                return EligibilityResult(
                    False,
                    "Material change requires reassessment before eligibility",
                    system_id=system.id,
                    agent_id=agent.id,
                    version_id=version.id,
                )

        if version.material_change_status == MaterialChangeStatus.PENDING.value:
            return EligibilityResult(
                False,
                "Material change analysis pending",
                system_id=system.id,
                agent_id=agent.id,
                version_id=version.id,
            )

        # Caller cannot widen authority via request metadata
        if caller_tools:
            declared = self._declared_tool_keys(version.id)
            for tool in caller_tools:
                if tool not in declared:
                    return EligibilityResult(
                        False,
                        f"Caller-declared tool {tool} not in approved version record",
                        system_id=system.id,
                        agent_id=agent.id,
                        version_id=version.id,
                    )

        # WP7 assurance / deployment gate contribution
        if not skip_assurance and environment:
            assurance_ok, assurance_reason = self._check_assurance(
                version.id, environment=environment
            )
            if not assurance_ok:
                return EligibilityResult(
                    False,
                    assurance_reason,
                    system_id=system.id,
                    agent_id=agent.id,
                    version_id=version.id,
                )

        return EligibilityResult(
            True,
            "Governance-eligible",
            system_id=system.id,
            agent_id=agent.id,
            version_id=version.id,
        )

    def _check_assurance(
        self, version_id: UUID, *, environment: str
    ) -> tuple[bool, str]:
        """Return (ok, reason) for WP7 environment assurance."""
        try:
            from rai_gateway.evaluations.service import EvaluationService

            svc = EvaluationService(self._db)
            if svc.is_environment_eligible(version_id, environment):
                return True, "Assurance valid"
            # Distinguish "no requirements" (already True) vs failed assurance
            from rai_gateway.models.registry import Agent, AgentVersion

            version = (
                self._db.query(AgentVersion)
                .filter(AgentVersion.id == version_id)
                .first()
            )
            if version is None:
                return False, "Agent version not found for assurance check"
            agent = self._db.query(Agent).filter(Agent.id == version.agent_id).first()
            if agent is None:
                return False, "Agent not found for assurance check"
            requirements = svc.resolve_requirements(
                ai_system_id=agent.ai_system_id, environment=environment
            )
            required = [r for r in requirements if r.required]
            if not required:
                return True, "No required evaluation requirements"
            return (
                False,
                f"WP7 {environment} assurance missing, expired, invalidated, or reassessment required",
            )
        except Exception as exc:  # noqa: BLE001 — fail closed on assurance errors
            return False, f"Assurance check failed closed: {exc}"

    def _resolve_system(
        self,
        system_id: UUID | str | None,
        system_key: str | None,
    ) -> AISystem | None:
        if system_id:
            return self._db.query(AISystem).filter(AISystem.id == system_id).first()
        if system_key:
            return (
                self._db.query(AISystem)
                .filter(AISystem.system_key == system_key)
                .first()
            )
        return None

    def _resolve_agent(
        self,
        agent_id: UUID | str | None,
        agent_key: str | None,
        system: AISystem,
    ) -> Agent | None:
        query = self._db.query(Agent).filter(Agent.ai_system_id == system.id)
        if agent_id:
            query = query.filter(Agent.id == agent_id)
        elif agent_key:
            query = query.filter(Agent.agent_key == agent_key)
        else:
            return None
        return query.first()

    def _resolve_version(
        self,
        agent: Agent,
        version_id: UUID | str | None,
        version_number: int | None,
    ) -> AgentVersion | None:
        query = self._db.query(AgentVersion).filter(AgentVersion.agent_id == agent.id)
        if version_id:
            return query.filter(AgentVersion.id == version_id).first()
        if version_number is not None:
            return query.filter(AgentVersion.version_number == version_number).first()
        return None

    def _declared_tool_keys(self, version_id: UUID) -> set[str]:
        from rai_gateway.models.registry import AgentVersionDependency, ToolResource

        deps = (
            self._db.query(AgentVersionDependency)
            .filter(
                AgentVersionDependency.agent_version_id == version_id,
                AgentVersionDependency.resource_type == "tool",
            )
            .all()
        )
        tool_ids = [d.resource_id for d in deps]
        if not tool_ids:
            return set()
        tools = self._db.query(ToolResource).filter(ToolResource.id.in_(tool_ids)).all()
        return {t.tool_key for t in tools}
