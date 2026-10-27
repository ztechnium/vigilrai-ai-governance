"""Instance departments and the default directory seed."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from rai_gateway.governance.errors import GovernanceNotFoundError
from rai_gateway.models.governance import Department

DEFAULT_DEPARTMENTS: tuple[tuple[str, str], ...] = (
    ("Marketing", "Brand, campaigns, and communications."),
    ("Management", "Leadership and organization management."),
    ("IT & Tech", "Technology operations and engineering."),
    ("Sales", "Revenue and customer acquisition."),
    ("R&D", "Research and product development."),
    ("Accounts", "Finance and accounting."),
    ("Security", "Security operations and access control."),
)


def ensure_default_departments(
    db: Session,
    *,
    created_by: str = "system",
    commit: bool = True,
) -> list[Department]:
    """Insert the starter departments. Existing names are kept."""
    rows = db.query(Department).all()
    by_name = {row.name: row for row in rows}
    pending: list[Department] = []
    for order, (name, description) in enumerate(DEFAULT_DEPARTMENTS):
        if name in by_name:
            continue
        row = Department(
            name=name,
            description=description,
            sort_order=order,
            created_by=created_by,
        )
        db.add(row)
        by_name[name] = row
        pending.append(row)
    if not pending:
        return sorted(by_name.values(), key=lambda row: (row.sort_order, row.name))
    try:
        with db.begin_nested():
            db.flush()
    except IntegrityError:
        for row in pending:
            db.expunge(row)
        rows = db.query(Department).all()
        return sorted(rows, key=lambda row: (row.sort_order, row.name))
    if commit:
        db.commit()
    return sorted(by_name.values(), key=lambda row: (row.sort_order, row.name))


def serialize_department(row: Department) -> dict[str, Any]:
    return {
        "id": str(row.id),
        "name": row.name,
        "description": row.description,
        "sort_order": row.sort_order,
    }


def require_department(db: Session, department_id: UUID) -> Department:
    row = db.query(Department).filter(Department.id == department_id).first()
    if row is None:
        raise GovernanceNotFoundError("Department not found")
    return row
