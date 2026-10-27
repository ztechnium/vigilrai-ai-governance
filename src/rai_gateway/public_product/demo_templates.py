"""Load developer-lab example templates for first-run seeding."""

from __future__ import annotations

import importlib.util
from functools import lru_cache
from pathlib import Path
from types import ModuleType
from typing import Any


class DemoTemplateError(Exception):
    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


def _catalog_path() -> Path:
    return (
        Path(__file__).resolve().parents[3]
        / "examples"
        / "developer_lab"
        / "catalog.py"
    )


@lru_cache(maxsize=1)
def catalog_module() -> ModuleType:
    path = _catalog_path()
    if not path.is_file():
        raise DemoTemplateError(f"Developer lab catalog is missing: {path}")
    spec = importlib.util.spec_from_file_location("rai_developer_lab_catalog", path)
    if spec is None or spec.loader is None:
        raise DemoTemplateError("Unable to load the developer lab catalog")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def list_template_summaries() -> list[dict[str, Any]]:
    module = catalog_module()
    summaries: list[dict[str, Any]] = []
    for system in module.SYSTEMS:
        tools = system.get("tools") or []
        model = system.get("model") or {}
        summaries.append(
            {
                "key": system["system_key"],
                "name": system["name"],
                "description": system.get("description") or "",
                "risk_tier": system.get("risk_tier"),
                "agent_name": system.get("agent_name"),
                "model_name": model.get("model_name"),
                "tools": [tool.get("name") or tool.get("tool_key") for tool in tools],
            }
        )
    return summaries


def template_by_key(key: str) -> dict[str, Any]:
    module = catalog_module()
    try:
        return module.system_by_key(key)
    except KeyError as exc:
        raise DemoTemplateError(f"Unknown demo template: {key}") from exc


def default_tool_url() -> str:
    return str(catalog_module().DEFAULT_TOOL_URL)
