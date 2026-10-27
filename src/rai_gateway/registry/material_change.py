"""Material change detection between agent versions."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from rai_gateway.models.registry import (
    AgentVersion,
    AgentVersionDependency,
    MaterialChangeRecord,
    ToolResource,
)
from rai_gateway.registry.domain import (
    AgentVersionStatus,
    ChangeCategory,
    MaterialChangeStatus,
)


@dataclass
class DetectedChange:
    change_category: ChangeCategory
    change_description: str
    is_material: bool
    reason: str
    previous_value: str | None
    current_value: str | None


def _dependency_key(dep: AgentVersionDependency) -> str:
    return f"{dep.resource_type}:{dep.resource_id}"


def _load_tool_map(db: Session, tool_ids: set[UUID]) -> dict[UUID, ToolResource]:
    if not tool_ids:
        return {}
    rows = db.query(ToolResource).filter(ToolResource.id.in_(tool_ids)).all()
    return {row.id: row for row in rows}


def compare_versions(
    db: Session,
    from_version: AgentVersion | None,
    to_version: AgentVersion,
    from_deps: list[AgentVersionDependency],
    to_deps: list[AgentVersionDependency],
) -> list[DetectedChange]:
    """Compare two agent versions and return detected governance changes."""
    changes: list[DetectedChange] = []

    from_dep_map = {_dependency_key(d): d for d in from_deps}
    to_dep_map = {_dependency_key(d): d for d in to_deps}

    from_tool_ids = {d.resource_id for d in from_deps if d.resource_type == "tool"}
    to_tool_ids = {d.resource_id for d in to_deps if d.resource_type == "tool"}
    tool_map = _load_tool_map(db, from_tool_ids | to_tool_ids)

    # Added dependencies
    for key, dep in to_dep_map.items():
        if key in from_dep_map:
            continue
        category = _resource_type_to_category(dep.resource_type)
        is_material = _is_material_addition(dep, tool_map)
        reason = _material_reason(dep, tool_map, added=True)
        changes.append(
            DetectedChange(
                change_category=category,
                change_description=f"Added {dep.resource_type} {dep.resource_id}",
                is_material=is_material,
                reason=reason,
                previous_value=None,
                current_value=key,
            )
        )

    # Removed dependencies
    for key, dep in from_dep_map.items():
        if key in to_dep_map:
            continue
        category = _resource_type_to_category(dep.resource_type)
        changes.append(
            DetectedChange(
                change_category=category,
                change_description=f"Removed {dep.resource_type} {dep.resource_id}",
                is_material=True,
                reason="Removal of declared governance dependency",
                previous_value=key,
                current_value=None,
            )
        )

    # Modified capabilities on shared dependencies
    for key in set(from_dep_map) & set(to_dep_map):
        prev = from_dep_map[key]
        curr = to_dep_map[key]
        if prev.capability_declaration != curr.capability_declaration:
            changes.append(
                DetectedChange(
                    change_category=ChangeCategory.PERMISSION,
                    change_description=f"Capability change on {key}",
                    is_material=True,
                    reason="Increased or changed permission/capability declaration",
                    previous_value=prev.capability_declaration,
                    current_value=curr.capability_declaration,
                )
            )

    # Risk tier change
    if from_version and from_version.risk_tier != to_version.risk_tier:
        changes.append(
            DetectedChange(
                change_category=ChangeCategory.RISK_TIER,
                change_description="Risk tier changed",
                is_material=True,
                reason="Risk tier change requires reassessment",
                previous_value=from_version.risk_tier,
                current_value=to_version.risk_tier,
            )
        )

    # Configuration digest change
    if (
        from_version
        and from_version.configuration_digest
        and to_version.configuration_digest
        and from_version.configuration_digest != to_version.configuration_digest
    ):
        changes.append(
            DetectedChange(
                change_category=ChangeCategory.CONFIGURATION,
                change_description="Configuration snapshot changed",
                is_material=True,
                reason="Governance-relevant configuration changed",
                previous_value=from_version.configuration_digest,
                current_value=to_version.configuration_digest,
            )
        )

    return changes


def _resource_type_to_category(resource_type: str) -> ChangeCategory:
    mapping = {
        "model": ChangeCategory.MODEL,
        "tool": ChangeCategory.TOOL,
        "mcp_server": ChangeCategory.MCP_SERVER,
        "external_service": ChangeCategory.EXTERNAL_SERVICE,
        "data_source": ChangeCategory.DATA_SOURCE,
    }
    return mapping.get(resource_type, ChangeCategory.CONFIGURATION)


def _is_material_addition(
    dep: AgentVersionDependency,
    tool_map: dict[UUID, ToolResource],
) -> bool:
    if dep.resource_type == "tool":
        tool = tool_map.get(dep.resource_id)
        if tool and tool.consequential_action:
            return True
    if dep.resource_type in ("mcp_server", "external_service", "data_source"):
        return True
    if dep.resource_type == "model":
        return True
    return False


def _material_reason(
    dep: AgentVersionDependency,
    tool_map: dict[UUID, ToolResource],
    *,
    added: bool,
) -> str:
    if dep.resource_type == "tool":
        tool = tool_map.get(dep.resource_id)
        if tool and tool.consequential_action:
            return f"New consequential tool: {tool.tool_key}"
        if tool:
            return f"New tool: {tool.tool_key}"
    action = "Added" if added else "Removed"
    return f"{action} {dep.resource_type} dependency"


def compute_configuration_digest(snapshot: dict[str, Any] | None) -> str | None:
    if not snapshot:
        return None
    payload = json.dumps(snapshot, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def apply_material_change_analysis(
    db: Session,
    to_version: AgentVersion,
    from_version: AgentVersion | None,
) -> list[DetectedChange]:
    """Analyze and persist material changes for a new version."""
    from_deps: list[AgentVersionDependency] = []
    if from_version:
        from_deps = (
            db.query(AgentVersionDependency)
            .filter(AgentVersionDependency.agent_version_id == from_version.id)
            .all()
        )

    to_deps = (
        db.query(AgentVersionDependency)
        .filter(AgentVersionDependency.agent_version_id == to_version.id)
        .all()
    )

    changes = compare_versions(db, from_version, to_version, from_deps, to_deps)

    # Clear prior records for this version
    db.query(MaterialChangeRecord).filter(
        MaterialChangeRecord.to_version_id == to_version.id
    ).delete()

    for change in changes:
        db.add(
            MaterialChangeRecord(
                from_version_id=from_version.id if from_version else None,
                to_version_id=to_version.id,
                change_category=change.change_category.value,
                change_description=change.change_description,
                is_material=change.is_material,
                reason=change.reason,
                previous_value=change.previous_value,
                current_value=change.current_value,
            )
        )

    has_material = any(c.is_material for c in changes)
    if has_material and from_version:
        to_version.material_change_status = MaterialChangeStatus.MATERIAL.value
        if to_version.lifecycle_status == AgentVersionStatus.DRAFT.value:
            to_version.lifecycle_status = AgentVersionStatus.REASSESSMENT_REQUIRED.value
        # WP7: material change requires selective reevaluation; never reuse prior assurance
        _notify_wp7_material_change(db, to_version, changes)
    elif changes:
        to_version.material_change_status = MaterialChangeStatus.NON_MATERIAL.value
    else:
        to_version.material_change_status = MaterialChangeStatus.NONE.value

    return changes


def _notify_wp7_material_change(
    db: Session,
    to_version: AgentVersion,
    changes: list[DetectedChange],
) -> None:
    """Create reassessment triggers for material changes (WP7 integration)."""
    try:
        from rai_gateway.evaluations.domain import (
            IMPACT_MAP,
            ReassessmentStatus,
            ReassessmentTriggerType,
        )
        from rai_gateway.models.evaluations import ReassessmentTrigger
        from rai_gateway.models.registry import Agent

        agent = db.query(Agent).filter(Agent.id == to_version.agent_id).first()
        if agent is None:
            return
        categories = sorted({c.change_category.value for c in changes if c.is_material})
        impacted: set[str] = set()
        for cat in categories:
            impacted |= set(IMPACT_MAP.get(cat, frozenset()))
        # Map change categories to trigger types
        trigger_type = ReassessmentTriggerType.MANUAL.value
        if "MODEL" in categories:
            trigger_type = ReassessmentTriggerType.MODEL_CHANGED.value
        elif "TOOL" in categories or "MCP_SERVER" in categories:
            trigger_type = ReassessmentTriggerType.TOOL_MCP_CHANGED.value
        elif "DATA_SOURCE" in categories:
            trigger_type = ReassessmentTriggerType.DATA_SOURCE_CHANGED.value
        elif "CONFIGURATION" in categories:
            trigger_type = ReassessmentTriggerType.SYSTEM_PROMPT_CHANGED.value

        db.add(
            ReassessmentTrigger(
                ai_system_id=agent.ai_system_id,
                agent_version_id=to_version.id,
                trigger_type=trigger_type,
                change_category=",".join(categories),
                impacted_categories=sorted(impacted) if impacted else None,
                status=ReassessmentStatus.REQUIRED.value,
                reason="Material change detected; selective reevaluation required",
                created_by="system",
            )
        )
    except Exception:
        # Do not break WP1 material-change path if WP7 tables are absent mid-migration
        pass
