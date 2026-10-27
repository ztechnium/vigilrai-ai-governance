"""Unit tests for material change detection."""

from __future__ import annotations

from uuid import uuid4

from rai_gateway.models.registry import (
    AgentVersion,
    AgentVersionDependency,
    ToolResource,
)
from rai_gateway.registry.material_change import compare_versions


def test_detects_consequential_tool_addition(db_session) -> None:
    tool = ToolResource(
        tool_key="Payments.create_transfer",
        name="Create Transfer",
        consequential_action=True,
    )
    db_session.add(tool)
    db_session.commit()

    from_version = AgentVersion(
        agent_id=uuid4(),
        version_number=1,
        lifecycle_status="APPROVED",
        created_by="tester",
    )
    to_version = AgentVersion(
        agent_id=from_version.agent_id,
        version_number=2,
        lifecycle_status="DRAFT",
        created_by="tester",
    )

    to_dep = AgentVersionDependency(
        agent_version_id=to_version.id,
        resource_type="tool",
        resource_id=tool.id,
    )

    changes = compare_versions(db_session, from_version, to_version, [], [to_dep])

    assert len(changes) == 1
    assert changes[0].is_material is True
    assert (
        "consequential" in changes[0].reason.lower() or "Payments" in changes[0].reason
    )
