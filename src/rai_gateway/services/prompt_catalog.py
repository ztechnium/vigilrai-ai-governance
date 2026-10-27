"""Prompt Catalog Service - Governance and lifecycle management."""

from typing import Any, Dict, List, Optional

from sqlalchemy import and_
from sqlalchemy.orm import Session
from sqlalchemy.sql import func

from rai_gateway.core.errors import PromptNotFoundError
from rai_gateway.core.observability import logger
from rai_gateway.models.database import Prompt, PromptAllowlist, PromptVersion


class PromptCatalogService:
    """Service for prompt governance and lifecycle management."""

    def __init__(self, db: Session):
        self.db = db

    async def resolve_prompt(
        self, prompt_id: str, version: int, trace_id: str
    ) -> Optional[Dict[str, Any]]:
        """
        Resolve prompt configuration for execution.

        Returns prompt template, policies, and configuration
        required for execution governance.
        """
        # Query for prompt version with approved status
        prompt_version = (
            self.db.query(PromptVersion)
            .filter(
                and_(
                    PromptVersion.prompt_id == prompt_id,
                    PromptVersion.version == version,
                    PromptVersion.status.in_(
                        ["active", "rai_approved"]
                    ),  # Only approved versions
                )
            )
            .first()
        )

        if not prompt_version:
            logger.warning(
                "prompt_not_found",
                prompt_id=prompt_id,
                version=version,
                trace_id=trace_id,
            )
            return None

        # Get base prompt info
        prompt = self.db.query(Prompt).filter(Prompt.prompt_id == prompt_id).first()

        if not prompt or prompt.status != "active":
            logger.warning("prompt_inactive", prompt_id=prompt_id, trace_id=trace_id)
            return None

        # Build configuration object
        config = {
            "prompt_id": prompt_id,
            "version": version,
            "name": prompt.name,
            "domain": prompt.domain,
            "template": prompt_version.template,
            "required_vars_schema": prompt_version.required_vars_schema,
            "expected_output_schema": prompt_version.expected_output_schema,
            "model_policy": prompt_version.model_policy,
            "policy_version": prompt_version.policy_version,
            "cache_policy": prompt_version.cache_policy or {},
            "case_policy": prompt_version.case_policy or {},
            "rag_policy": prompt_version.rag_policy or {},
            "judge_policy": prompt_version.judge_policy or {},
            "xai_policy": prompt_version.xai_policy or {},
            "status": prompt_version.status,
            "approved_by": prompt_version.approved_by,
            "approved_at": prompt_version.approved_at,
        }

        logger.info(
            "prompt_resolved",
            prompt_id=prompt_id,
            version=version,
            status=prompt_version.status,
            trace_id=trace_id,
        )

        return config

    async def check_allowlist(
        self, prompt_id: str, version: int, system_id: str, module: str, trace_id: str
    ) -> bool:
        """
        Check if system/module is allowed to use this prompt version.

        Implements fail-closed allowlist enforcement.
        """
        # Query allowlist entry
        allowlist_entry = (
            self.db.query(PromptAllowlist)
            .filter(
                and_(
                    PromptAllowlist.prompt_id == prompt_id,
                    PromptAllowlist.version == version,
                    PromptAllowlist.system_id == system_id,
                    PromptAllowlist.module == module,
                    PromptAllowlist.allowed,
                )
            )
            .first()
        )

        allowed = allowlist_entry is not None

        logger.info(
            "allowlist_check",
            prompt_id=prompt_id,
            version=version,
            system_id=system_id,
            module=module,
            allowed=allowed,
            trace_id=trace_id,
        )

        return allowed

    async def get_prompt_rai_rules(
        self, prompt_id: str, version: int, trace_id: str
    ) -> List[Dict[str, Any]]:
        """Get RAI rules bound to this prompt version."""
        # This would join with PromptRaiRule and RaiRule tables
        # For now, return empty list (rules will be implemented in RAI Guard service)
        return []

    async def create_prompt(
        self,
        prompt_id: str,
        name: str,
        domain: str,
        description: str,
        owner_system_id: str,
        trace_id: str,
    ) -> Prompt:
        """Create a new prompt (admin function)."""
        # Check if prompt already exists
        existing = self.db.query(Prompt).filter(Prompt.prompt_id == prompt_id).first()

        if existing:
            raise ValueError(f"Prompt {prompt_id} already exists")

        prompt = Prompt(
            prompt_id=prompt_id,
            name=name,
            domain=domain,
            description=description,
            owner_system_id=owner_system_id,
            status="active",
        )

        self.db.add(prompt)
        self.db.commit()

        logger.info(
            "prompt_created",
            prompt_id=prompt_id,
            name=name,
            domain=domain,
            owner_system_id=owner_system_id,
            trace_id=trace_id,
        )

        return prompt

    async def create_prompt_version(
        self,
        prompt_id: str,
        version: int,
        template: str,
        required_vars_schema: Dict[str, Any],
        model_policy: Dict[str, Any],
        policy_version: str,
        created_by: str,
        trace_id: str,
        **kwargs,
    ) -> PromptVersion:
        """Create a new prompt version (starts as draft)."""
        prompt_version = PromptVersion(
            prompt_id=prompt_id,
            version=version,
            status="draft",
            template=template,
            required_vars_schema=required_vars_schema,
            model_policy=model_policy,
            policy_version=policy_version,
            created_by=created_by,
            expected_output_schema=kwargs.get("expected_output_schema"),
            cache_policy=kwargs.get("cache_policy"),
            case_policy=kwargs.get("case_policy"),
            rag_policy=kwargs.get("rag_policy"),
            judge_policy=kwargs.get("judge_policy"),
            xai_policy=kwargs.get("xai_policy"),
            review_prompt_template=kwargs.get("review_prompt_template"),
        )

        self.db.add(prompt_version)
        self.db.commit()

        logger.info(
            "prompt_version_created",
            prompt_id=prompt_id,
            version=version,
            status="draft",
            created_by=created_by,
            trace_id=trace_id,
        )

        return prompt_version

    async def approve_prompt_version(
        self,
        prompt_id: str,
        version: int,
        approval_type: str,  # 'biz_approved' or 'rai_approved'
        approved_by: str,
        trace_id: str,
    ) -> PromptVersion:
        """Approve a prompt version (governance workflow)."""
        prompt_version = (
            self.db.query(PromptVersion)
            .filter(
                and_(
                    PromptVersion.prompt_id == prompt_id,
                    PromptVersion.version == version,
                )
            )
            .first()
        )

        if not prompt_version:
            raise PromptNotFoundError(f"Prompt version {prompt_id}:{version} not found")

        # Status progression: draft -> biz_approved -> rai_approved -> active
        if approval_type == "biz_approved" and prompt_version.status == "draft":
            prompt_version.status = "biz_approved"
        elif (
            approval_type == "rai_approved" and prompt_version.status == "biz_approved"
        ):
            prompt_version.status = "active"  # RAI approval makes it active
        else:
            raise ValueError(
                f"Invalid approval transition: {prompt_version.status} -> {approval_type}"
            )

        prompt_version.approved_by = approved_by
        prompt_version.approved_at = func.now()

        self.db.commit()

        logger.info(
            "prompt_version_approved",
            prompt_id=prompt_id,
            version=version,
            approval_type=approval_type,
            approved_by=approved_by,
            new_status=prompt_version.status,
            trace_id=trace_id,
        )

        return prompt_version
