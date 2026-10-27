"""Validate proposed actions against WP2 effective authority."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy.orm import Session

from rai_gateway.approval.domain import ApprovalDenialCode, ProposedAction
from rai_gateway.approval.errors import ApprovalDeniedError
from rai_gateway.identity.domain import DelegationScope, ResourceScopeMode
from rai_gateway.identity.resolver import RuntimeAuthorityContext
from rai_gateway.identity.version_resources import (
    VersionResourceCatalog,
    load_version_resource_catalog,
)
from rai_gateway.models.registry import ToolResource


def _allowed_ids_from_scope(dimension, version_ids: set[str]) -> set[str]:
    return dimension.resolve_against(version_ids)


class ActionAuthorityValidator:
    """Fail-closed validation of proposed actions against WP2 authority."""

    def __init__(self, db: Session) -> None:
        self._db = db

    def validate(
        self,
        authority: RuntimeAuthorityContext,
        action: ProposedAction,
    ) -> None:
        identity = authority.runtime_identity
        if action.runtime_identity_id != identity.id:
            raise ApprovalDeniedError(
                ApprovalDenialCode.APPROVAL_RUNTIME_IDENTITY_MISMATCH,
                "Proposed action runtime identity does not match authority context",
            )
        if action.agent_version_id != authority.agent_version.id:
            raise ApprovalDeniedError(
                ApprovalDenialCode.APPROVAL_AGENT_VERSION_MISMATCH,
                "Proposed action agent version does not match authority context",
            )
        if action.agent_id != authority.agent.id:
            raise ApprovalDeniedError(
                ApprovalDenialCode.APPROVAL_AGENT_VERSION_MISMATCH,
                "Proposed action agent does not match authority context",
            )
        if action.ai_system_id != authority.ai_system.id:
            raise ApprovalDeniedError(
                ApprovalDenialCode.APPROVAL_AUTHORITY_CHANGED,
                "Proposed action AI system does not match authority context",
            )

        catalog = load_version_resource_catalog(self._db, authority.agent_version.id)
        scope = authority.effective_scope

        self._validate_resources(action, catalog, scope)

    def _validate_resources(
        self,
        action: ProposedAction,
        catalog: VersionResourceCatalog,
        scope: DelegationScope,
    ) -> None:
        allowed_models = _allowed_ids_from_scope(scope.models, catalog.model_ids)
        allowed_data_sources = _allowed_ids_from_scope(
            scope.data_sources, catalog.data_source_ids
        )
        allowed_mcps = _allowed_ids_from_scope(
            scope.mcp_servers, catalog.mcp_server_ids
        )
        allowed_tools = _allowed_ids_from_scope(scope.tools, catalog.tool_ids)

        if action.model_id and str(action.model_id) not in allowed_models:
            raise ApprovalDeniedError(
                ApprovalDenialCode.AUTHORITY_SCOPE_EXCEEDED,
                "Requested model is outside effective authority",
            )
        if (
            action.data_source_id
            and str(action.data_source_id) not in allowed_data_sources
        ):
            raise ApprovalDeniedError(
                ApprovalDenialCode.AUTHORITY_SCOPE_EXCEEDED,
                "Requested data source is outside effective authority",
            )
        if action.integration_type == "mcp" and action.integration_id:
            if str(action.integration_id) not in allowed_mcps:
                raise ApprovalDeniedError(
                    ApprovalDenialCode.AUTHORITY_SCOPE_EXCEEDED,
                    "Requested MCP server is outside effective authority",
                )
        if action.tool_id:
            tool_id = str(action.tool_id)
            if tool_id not in allowed_tools:
                raise ApprovalDeniedError(
                    ApprovalDenialCode.AUTHORITY_SCOPE_EXCEEDED,
                    "Requested tool is outside effective authority",
                )
            tool = catalog.tool_by_id(tool_id)
            if tool and tool.mcp_server_id and tool.mcp_server_id not in allowed_mcps:
                raise ApprovalDeniedError(
                    ApprovalDenialCode.AUTHORITY_SCOPE_EXCEEDED,
                    "Tool MCP parent is outside effective authority",
                )

        if (
            scope.environments.mode == ResourceScopeMode.EXPLICIT
            and action.environment
            and action.environment not in scope.environments.ids
        ):
            raise ApprovalDeniedError(
                ApprovalDenialCode.AUTHORITY_SCOPE_EXCEEDED,
                "Requested environment is outside effective authority",
            )

    def resolve_tool_metadata(self, tool_id: UUID | None) -> ToolResource | None:
        if not tool_id:
            return None
        return self._db.query(ToolResource).filter(ToolResource.id == tool_id).first()
