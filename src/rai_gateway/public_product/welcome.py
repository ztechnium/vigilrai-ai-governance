"""First-run welcome profile, template choice, and completion."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from rai_gateway.models.governance import OrganizationGovernanceProfile
from rai_gateway.models.productization import OrganizationOnboarding, SdkIntegration
from rai_gateway.public_product.demo_seed import DemoSeedError, seed_demo_template
from rai_gateway.public_product.demo_templates import (
    DemoTemplateError,
    list_template_summaries,
)
from rai_gateway.public_product.onboarding import OnboardingError, OnboardingService

_MAX_LOGO_CHARS = 700_000
_SINGLETON_KEY = "default"


class WelcomeError(Exception):
    def __init__(self, message: str, *, http_status: int = 400) -> None:
        super().__init__(message)
        self.message = message
        self.http_status = http_status


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class WelcomeService:
    def __init__(self, db: Session) -> None:
        self._db = db

    def get_state(self) -> dict[str, Any]:
        profile = self._profile()
        record = OnboardingService(self._db).get_record()
        try:
            templates = list_template_summaries()
        except DemoTemplateError as exc:
            raise WelcomeError(exc.message, http_status=500) from exc
        return {
            "welcome_completed": bool(record and record.welcome_completed_at),
            "welcome_completed_at": (
                record.welcome_completed_at.isoformat()
                if record and record.welcome_completed_at
                else None
            ),
            "organization": {
                "name": profile.name,
                "description": profile.description,
                "legal_name": profile.legal_name,
                "logo": profile.logo,
                "industry": profile.sector,
            },
            "setup": self._setup(record),
            "templates": templates,
        }

    def update_profile(
        self,
        *,
        name: str,
        industry: str,
        logo: str | None,
        actor: str,
    ) -> dict[str, Any]:
        profile = self._profile()
        cleaned_name = name.strip()
        cleaned_industry = industry.strip()
        if not cleaned_name:
            raise WelcomeError("Organization name is required")
        if not cleaned_industry:
            raise WelcomeError("Industry is required")
        if len(cleaned_name) > 200:
            raise WelcomeError("Organization name is too long")
        if len(cleaned_industry) > 80:
            raise WelcomeError("Industry is too long")

        if logo is not None:
            cleaned_logo = logo.strip()
            if cleaned_logo and not cleaned_logo.startswith("data:image/"):
                raise WelcomeError("Logo must be an image upload")
            if len(cleaned_logo) > _MAX_LOGO_CHARS:
                raise WelcomeError("Logo image is too large")
            profile.logo = cleaned_logo or None

        profile.name = cleaned_name
        profile.legal_name = cleaned_name
        profile.sector = cleaned_industry
        profile.updated_by = actor
        self._db.commit()

        OnboardingService(self._db).update(complete_step="organization_profile")
        return self.get_state()

    def seed_template(self, *, template_key: str, actor: str) -> dict[str, Any]:
        try:
            seeded = seed_demo_template(
                self._db,
                template_key=template_key,
                actor=actor,
            )
        except DemoSeedError as exc:
            raise WelcomeError(exc.message, http_status=exc.http_status) from exc
        state = self.get_state()
        return {**state, "seeded": seeded}

    def complete(self) -> dict[str, Any]:
        service = OnboardingService(self._db)
        record = service.get_or_create()
        if record.welcome_completed_at is None:
            record.welcome_completed_at = _utcnow()
            self._db.commit()
            self._db.refresh(record)
        return self.get_state()

    def _profile(self) -> OrganizationGovernanceProfile:
        profile = (
            self._db.query(OrganizationGovernanceProfile)
            .filter(OrganizationGovernanceProfile.singleton_key == _SINGLETON_KEY)
            .first()
        )
        if profile is None:
            profile = OrganizationGovernanceProfile(
                singleton_key=_SINGLETON_KEY,
                name="Organization",
                legal_name="Organization",
            )
            self._db.add(profile)
            self._db.flush()
        return profile

    def _setup(self, record: OrganizationOnboarding | None) -> dict[str, Any] | None:
        if record is None or (
            record.first_integration_id is None and record.first_ai_system_id is None
        ):
            return None
        integration = None
        if record.first_integration_id is not None:
            integration = (
                self._db.query(SdkIntegration)
                .filter(SdkIntegration.id == record.first_integration_id)
                .first()
            )
        metadata = (integration.metadata_json or {}) if integration else {}
        return {
            "template_key": metadata.get("template_key"),
            "ai_system_id": str(record.first_ai_system_id)
            if record.first_ai_system_id
            else None,
            "integration_id": str(record.first_integration_id)
            if record.first_integration_id
            else None,
            "tool_name": metadata.get("tool_name"),
        }


def welcome_http_error(
    exc: WelcomeError | OnboardingError,
) -> tuple[int, dict[str, str]]:
    return exc.http_status, {"error": "INVALID_REQUEST", "message": exc.message}
