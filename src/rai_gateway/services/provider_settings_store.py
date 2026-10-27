"""Persistence helpers for provider runtime settings."""

from __future__ import annotations

from typing import Any, Dict

from sqlalchemy.orm import Session

from rai_gateway.core.config import settings
from rai_gateway.models.database import ProviderSetting

SETTING_ATTR_MAP: Dict[str, str] = {
    "default_provider": "llm_provider",
    "default_model": "llm_provider_model",
    "llm_provider_url": "llm_provider_url",
    "llm_provider_api_key": "llm_provider_api_key",
    "azure_openai_api_key": "azure_openai_api_key",
    "azure_openai_endpoint": "azure_openai_endpoint",
    "azure_openai_deployment": "azure_openai_deployment",
    "azure_openai_api_version": "azure_openai_api_version",
    "anthropic_api_key": "anthropic_api_key",
    "aws_region": "aws_region",
    "gcp_project_id": "gcp_project_id",
    "gcp_location": "gcp_location",
    "ollama_endpoint": "ollama_endpoint",
}


def _runtime_value(setting_key: str) -> Any:
    attr = SETTING_ATTR_MAP[setting_key]
    return getattr(settings, attr, None)


def _set_runtime_value(setting_key: str, value: Any) -> None:
    attr = SETTING_ATTR_MAP[setting_key]
    setattr(settings, attr, value)


def persist_provider_settings(db: Session, payload: Dict[str, Any]) -> None:
    """Upsert provider settings into DB and apply to in-memory runtime settings."""
    for key, value in payload.items():
        if key not in SETTING_ATTR_MAP:
            continue
        _set_runtime_value(key, value)
        row = (
            db.query(ProviderSetting).filter(ProviderSetting.setting_key == key).first()
        )
        string_value = None if value is None else str(value)
        if row:
            row.setting_value = string_value
        else:
            db.add(ProviderSetting(setting_key=key, setting_value=string_value))


def _parse_value(setting_key: str, raw: str | None) -> Any:
    if raw is None:
        return None
    # Keep all provider settings as string-like runtime config values.
    return raw


def load_provider_settings_into_runtime(
    db: Session, bootstrap_from_runtime: bool = True
) -> Dict[str, Any]:
    """Load persisted provider settings into runtime settings.

    If table is empty and bootstrap_from_runtime is true, seed the table using current
    environment/runtime values so values persist across restarts.
    """
    rows = db.query(ProviderSetting).all()

    if not rows and bootstrap_from_runtime:
        seed_payload = {
            key: _runtime_value(key)
            for key in SETTING_ATTR_MAP
            if _runtime_value(key) is not None and str(_runtime_value(key)) != ""
        }
        persist_provider_settings(db, seed_payload)
        db.commit()
        rows = db.query(ProviderSetting).all()

    loaded: Dict[str, Any] = {}
    for row in rows:
        if row.setting_key not in SETTING_ATTR_MAP:
            continue
        value = _parse_value(row.setting_key, row.setting_value)
        _set_runtime_value(row.setting_key, value)
        loaded[row.setting_key] = value

    return loaded
