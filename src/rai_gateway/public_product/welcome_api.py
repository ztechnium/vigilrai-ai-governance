"""Authenticated first-run welcome routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from rai_gateway.core.authorization import require_permission
from rai_gateway.core.database import get_db
from rai_gateway.core.tenant_context import TenantContext
from rai_gateway.public_product.onboarding import OnboardingError
from rai_gateway.public_product.welcome import WelcomeError, WelcomeService

router = APIRouter(prefix="/v1/productization", tags=["productization"])


class WelcomeProfileBody(BaseModel):
    name: str
    industry: str
    logo: str | None = None


class WelcomeSeedBody(BaseModel):
    template_key: str


def _raise_welcome(exc: WelcomeError | OnboardingError) -> None:
    raise HTTPException(
        status_code=exc.http_status,
        detail={"error": "INVALID_REQUEST", "message": exc.message},
    ) from exc


@router.get("/welcome")
def get_welcome(
    db: Session = Depends(get_db),
    _tenant: TenantContext = Depends(require_permission("sdk:read")),
):
    try:
        return WelcomeService(db).get_state()
    except (WelcomeError, OnboardingError) as exc:
        _raise_welcome(exc)


@router.patch("/welcome/profile")
def update_welcome_profile(
    body: WelcomeProfileBody,
    db: Session = Depends(get_db),
    tenant: TenantContext = Depends(require_permission("sdk:manage")),
):
    try:
        return WelcomeService(db).update_profile(
            name=body.name,
            industry=body.industry,
            logo=body.logo,
            actor=tenant.user_id,
        )
    except (WelcomeError, OnboardingError) as exc:
        _raise_welcome(exc)


@router.post("/welcome/seed")
def seed_welcome_template(
    body: WelcomeSeedBody,
    db: Session = Depends(get_db),
    tenant: TenantContext = Depends(require_permission("sdk:manage")),
):
    try:
        return WelcomeService(db).seed_template(
            template_key=body.template_key,
            actor=tenant.user_id,
        )
    except (WelcomeError, OnboardingError) as exc:
        _raise_welcome(exc)


@router.post("/welcome/complete")
def complete_welcome(
    db: Session = Depends(get_db),
    _tenant: TenantContext = Depends(require_permission("sdk:manage")),
):
    try:
        return WelcomeService(db).complete()
    except (WelcomeError, OnboardingError) as exc:
        _raise_welcome(exc)
