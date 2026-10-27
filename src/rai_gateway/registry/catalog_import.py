"""Import organization catalog rows from the Catalog worksheet."""

from __future__ import annotations

from io import BytesIO
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from rai_gateway.models.registry import (
    ExternalService,
    MCPServer,
    ModelResource,
    ToolResource,
)
from rai_gateway.registry.domain import CatalogScope
from rai_gateway.registry.errors import DuplicateKeyError, RegistryError
from rai_gateway.registry.service import RegistryService

SHEET_HEADERS = (
    "type",
    "key",
    "name",
    "provider",
    "description",
    "model_name",
    "model_version",
    "endpoint",
    "category",
    "sensitivity",
    "consequential",
    "mcp_key",
)
_TYPES = {"model", "mcp", "tool", "service"}
_MAX_ROWS = 500
_MAX_BYTES = 2_000_000
_CATALOG_SHEET = "Catalog"
_EXAMPLE_SHEET = "Example"
# Sample rows for the Example sheet. Import reads the Catalog sheet only.
EXAMPLE_ROWS: tuple[tuple[str, ...], ...] = (
    (
        "model",
        "gemini-2.5-pro",
        "Gemini 2.5 Pro",
        "Google",
        "Sample model. Put your own rows on the Catalog sheet.",
        "gemini-2.5-pro",
        "2.5",
        "",
        "",
        "",
        "",
        "",
    ),
    (
        "model",
        "claude-sonnet-4",
        "Claude Sonnet 4",
        "Anthropic",
        "Sample Claude model. model_name is required for type model.",
        "claude-sonnet-4",
        "4",
        "",
        "",
        "",
        "",
        "",
    ),
    (
        "model",
        "gpt-4o",
        "GPT-4o",
        "OpenAI",
        "Sample GPT model. key is the stable id used on later uploads.",
        "gpt-4o",
        "4o",
        "",
        "",
        "",
        "",
        "",
    ),
    (
        "mcp",
        "github",
        "GitHub",
        "GitHub",
        "Sample MCP server. Tools refer to this key in mcp_key.",
        "",
        "",
        "https://example.invalid/github",
        "development",
        "",
        "",
        "",
    ),
    (
        "tool",
        "github.search",
        "Search code",
        "GitHub",
        "Sample tool. consequential is yes or no.",
        "",
        "",
        "",
        "search",
        "low",
        "no",
        "github",
    ),
    (
        "service",
        "billing-api",
        "Billing API",
        "Internal",
        "Sample external service.",
        "",
        "",
        "https://billing.example.invalid",
        "",
        "internal",
        "",
        "",
    ),
)


class CatalogImportError(Exception):
    def __init__(self, message: str, *, http_status: int = 400) -> None:
        super().__init__(message)
        self.message = message
        self.http_status = http_status


def template_workbook_bytes() -> bytes:
    from openpyxl import Workbook

    workbook = Workbook()
    catalog = workbook.active
    catalog.title = _CATALOG_SHEET
    catalog.append(list(SHEET_HEADERS))
    example = workbook.create_sheet(_EXAMPLE_SHEET)
    example.append(list(SHEET_HEADERS))
    for row in EXAMPLE_ROWS:
        example.append(list(row))
    buffer = BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


def import_catalog_workbook(
    db: Session,
    *,
    content: bytes,
) -> dict[str, Any]:
    if len(content) > _MAX_BYTES:
        raise CatalogImportError("Workbook is too large")
    rows = _parse_rows(content)
    if not rows:
        raise CatalogImportError("Workbook has no catalog rows")
    mcp_keys = {row["key"] for row in rows if row["type"] == "mcp"}
    registry = RegistryService(db)
    existing_mcp = {
        row.server_key: row
        for row in db.query(MCPServer)
        .filter(MCPServer.scope == CatalogScope.ORGANIZATION.value)
        .all()
    }
    for row in rows:
        if row["type"] != "tool":
            continue
        mcp_key = row.get("mcp_key") or ""
        if mcp_key and mcp_key not in mcp_keys and mcp_key not in existing_mcp:
            raise CatalogImportError(
                f"Row {row['row_number']}: mcp_key '{mcp_key}' is not in this sheet or the catalog"
            )
    created = 0
    updated = 0
    ordered = sorted(
        rows,
        key=lambda row: {"mcp": 0, "model": 1, "service": 2, "tool": 3}[row["type"]],
    )
    mcp_ids: dict[str, UUID] = {key: row.id for key, row in existing_mcp.items()}
    try:
        for row in ordered:
            action, mcp_id = _apply_row(
                db,
                registry,
                row,
                mcp_ids,
            )
            if mcp_id is not None and row["type"] == "mcp":
                mcp_ids[row["key"]] = mcp_id
            if action == "created":
                created += 1
            else:
                updated += 1
    except RegistryError as exc:
        raise CatalogImportError(exc.message, http_status=exc.status_code) from exc
    return {"created": created, "updated": updated, "rows": len(rows)}


def _parse_rows(content: bytes) -> list[dict[str, Any]]:
    try:
        from openpyxl import load_workbook
    except ImportError as exc:
        raise CatalogImportError(
            "Excel support is not installed", http_status=500
        ) from exc
    try:
        workbook = load_workbook(BytesIO(content), read_only=True, data_only=True)
    except Exception as exc:
        raise CatalogImportError("Workbook could not be read") from exc
    sheet = (
        workbook[_CATALOG_SHEET]
        if _CATALOG_SHEET in workbook.sheetnames
        else workbook.active
    )
    iterator = sheet.iter_rows(values_only=True)
    try:
        header = next(iterator)
    except StopIteration as exc:
        raise CatalogImportError("Workbook is empty") from exc
    labels = [str(cell).strip().lower() if cell is not None else "" for cell in header]
    missing = [name for name in ("type", "key", "name") if name not in labels]
    if missing:
        raise CatalogImportError("Workbook is missing columns: " + ", ".join(missing))
    index = {label: pos for pos, label in enumerate(labels) if label}
    parsed: list[dict[str, Any]] = []
    for offset, raw in enumerate(iterator, start=2):
        if offset - 1 > _MAX_ROWS:
            raise CatalogImportError(f"Workbook exceeds {_MAX_ROWS} data rows")
        values = _row_dict(raw, index)
        if not any(values.values()):
            continue
        kind = (values.get("type") or "").strip().lower()
        key = (values.get("key") or "").strip()
        name = (values.get("name") or "").strip()
        if kind not in _TYPES:
            raise CatalogImportError(
                f"Row {offset}: type must be model, mcp, tool, or service"
            )
        if not key:
            raise CatalogImportError(f"Row {offset}: key is required")
        if kind != "model" and not name:
            raise CatalogImportError(f"Row {offset}: name is required")
        if kind == "model" and not (values.get("provider") or "").strip():
            raise CatalogImportError(f"Row {offset}: provider is required for a model")
        if kind == "model" and not (
            (values.get("model_name") or "").strip() or name or key
        ):
            raise CatalogImportError(f"Row {offset}: model_name is required")
        parsed.append(
            {**values, "row_number": offset, "type": kind, "key": key, "name": name}
        )
    return parsed


def _row_dict(raw: tuple[Any, ...], index: dict[str, int]) -> dict[str, str]:
    result: dict[str, str] = {}
    for label, pos in index.items():
        if pos >= len(raw) or raw[pos] is None:
            result[label] = ""
        else:
            result[label] = str(raw[pos]).strip()
    return result


def _boolish(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "y"}


def _apply_row(
    db: Session,
    registry: RegistryService,
    row: dict[str, Any],
    mcp_ids: dict[str, UUID],
) -> tuple[str, UUID | None]:
    kind = row["type"]
    if kind == "model":
        return _upsert_model(db, registry, row), None
    if kind == "mcp":
        server, action = _upsert_mcp(db, registry, row)
        return action, server.id
    if kind == "service":
        return _upsert_service(db, registry, row), None
    tool, action = _upsert_tool(db, registry, row, mcp_ids)
    return action, tool.id


def _upsert_model(
    db: Session,
    registry: RegistryService,
    row: dict[str, Any],
) -> str:
    model_name = (row.get("model_name") or row.get("name") or row["key"]).strip()
    model_version = (row.get("model_version") or "").strip() or None
    provider = row["provider"].strip()
    existing = _find_model(db, row["key"], provider, model_name, model_version)
    if existing:
        if row.get("name"):
            existing.model_name = model_name
        existing.provider = provider
        if model_version:
            existing.model_version = model_version
        if row.get("endpoint"):
            existing.deployment_reference = row["endpoint"]
        metadata = dict(existing.metadata_ or {})
        metadata["import_key"] = row["key"]
        existing.metadata_ = metadata
        db.commit()
        return "updated"
    registry.create_model_resource(
        scope=CatalogScope.ORGANIZATION.value,
        provider=provider,
        model_name=model_name,
        model_version=model_version,
        deployment_reference=row.get("endpoint") or None,
        hosting_type="EXTERNAL_API",
        metadata={"import_key": row["key"]},
    )
    return "created"


def _find_model(
    db: Session,
    key: str,
    provider: str,
    model_name: str,
    model_version: str | None,
) -> ModelResource | None:
    rows = (
        db.query(ModelResource)
        .filter(ModelResource.scope == CatalogScope.ORGANIZATION.value)
        .all()
    )
    for item in rows:
        if (item.metadata_ or {}).get("import_key") == key:
            return item
    for item in rows:
        if (
            item.provider == provider
            and item.model_name == model_name
            and (item.model_version or None) == model_version
        ):
            return item
    return None


def _upsert_mcp(
    db: Session,
    registry: RegistryService,
    row: dict[str, Any],
) -> tuple[MCPServer, str]:
    existing = (
        db.query(MCPServer)
        .filter(
            MCPServer.scope == CatalogScope.ORGANIZATION.value,
            MCPServer.server_key == row["key"],
        )
        .first()
    )
    if existing:
        existing.name = row["name"]
        if row.get("description"):
            existing.description = row["description"]
        if row.get("provider"):
            existing.provider = row["provider"]
        if row.get("endpoint"):
            existing.endpoint_reference = row["endpoint"]
        db.commit()
        return existing, "updated"
    try:
        created = registry.create_mcp_server(
            scope=CatalogScope.ORGANIZATION.value,
            server_key=row["key"],
            name=row["name"],
            description=row.get("description") or None,
            provider=row.get("provider") or None,
            endpoint_reference=row.get("endpoint") or None,
            environment="development",
        )
    except DuplicateKeyError:
        existing = (
            db.query(MCPServer)
            .filter(
                MCPServer.scope == CatalogScope.ORGANIZATION.value,
                MCPServer.server_key == row["key"],
            )
            .one()
        )
        return existing, "updated"
    return created, "created"


def _upsert_service(
    db: Session,
    registry: RegistryService,
    row: dict[str, Any],
) -> str:
    existing = (
        db.query(ExternalService)
        .filter(
            ExternalService.scope == CatalogScope.ORGANIZATION.value,
            ExternalService.service_key == row["key"],
        )
        .first()
    )
    if existing:
        existing.name = row["name"]
        if row.get("description"):
            existing.description = row["description"]
        if row.get("provider"):
            existing.provider = row["provider"]
        if row.get("endpoint"):
            existing.endpoint_reference = row["endpoint"]
        if row.get("sensitivity"):
            existing.sensitivity = row["sensitivity"]
        db.commit()
        return "updated"
    registry.create_external_service(
        scope=CatalogScope.ORGANIZATION.value,
        service_key=row["key"],
        name=row["name"],
        description=row.get("description") or None,
        provider=row.get("provider") or None,
        endpoint_reference=row.get("endpoint") or None,
        sensitivity=row.get("sensitivity") or None,
        environment="development",
    )
    return "created"


def _upsert_tool(
    db: Session,
    registry: RegistryService,
    row: dict[str, Any],
    mcp_ids: dict[str, UUID],
) -> tuple[ToolResource, str]:
    mcp_id = mcp_ids.get(row.get("mcp_key") or "")
    existing = (
        db.query(ToolResource)
        .filter(
            ToolResource.scope == CatalogScope.ORGANIZATION.value,
            ToolResource.tool_key == row["key"],
        )
        .first()
    )
    if existing:
        existing.name = row["name"]
        if row.get("description"):
            existing.description = row["description"]
        if row.get("provider"):
            existing.provider = row["provider"]
        if row.get("category"):
            existing.category = row["category"]
        if row.get("sensitivity"):
            existing.sensitivity = row["sensitivity"]
        if row.get("consequential"):
            existing.consequential_action = _boolish(row["consequential"])
        if mcp_id:
            existing.mcp_server_id = mcp_id
        db.commit()
        return existing, "updated"
    created = registry.create_tool_resource(
        scope=CatalogScope.ORGANIZATION.value,
        tool_key=row["key"],
        name=row["name"],
        description=row.get("description") or None,
        category=row.get("category") or None,
        provider=row.get("provider") or None,
        sensitivity=row.get("sensitivity") or None,
        consequential_action=_boolish(row.get("consequential") or ""),
        mcp_server_id=mcp_id,
    )
    return created, "created"
