"""
AI system inventory CLI.

This edition has one instance. AI systems are not assigned to organizations.
"""

import sys

import click
from sqlalchemy.orm import Session

from rai_gateway.core.database import SessionLocal, init_db
from rai_gateway.models.registry import AISystem


def list_ai_systems(db: Session) -> list[AISystem]:
    return db.query(AISystem).order_by(AISystem.created_at.asc()).all()


@click.group()
def orphan_cleanup():
    """List AI systems on this single instance."""
    pass


@orphan_cleanup.command()
@click.option(
    "--format", "fmt", type=click.Choice(["table", "json", "csv"]), default="table"
)
def report(fmt: str):
    """List AI systems registered on this instance."""
    import json

    db = None
    try:
        init_db()
        db = SessionLocal()
        systems = list_ai_systems(db)
        if not systems:
            click.echo("No AI systems found.")
            return
        if fmt == "json":
            click.echo(
                json.dumps(
                    [
                        {
                            "id": str(row.id),
                            "system_key": row.system_key,
                            "name": row.name,
                            "status": row.status,
                            "created_by": row.created_by,
                        }
                        for row in systems
                    ],
                    indent=2,
                )
            )
            return
        if fmt == "csv":
            click.echo("id,system_key,name,status,created_by")
            for row in systems:
                click.echo(
                    f"{row.id},{row.system_key},{row.name},{row.status},{row.created_by}"
                )
            return
        click.echo(f"\n{len(systems)} AI system(s) on this instance:\n")
        click.echo(f"{'ID':<38} {'System Key':<30} {'Name':<40} {'Status':<16}")
        click.echo("=" * 128)
        for row in systems:
            click.echo(
                f"{str(row.id):<38} {row.system_key:<30} {(row.name or '')[:39]:<40} {row.status:<16}"
            )
    except Exception as exc:
        click.echo(f"Error: {exc}", err=True)
        sys.exit(1)
    finally:
        if db is not None:
            db.close()


@orphan_cleanup.command()
def verify():
    """Confirm AI systems are stored without an organization assignment."""
    db = None
    try:
        init_db()
        db = SessionLocal()
        total = db.query(AISystem).count()
        click.echo(f"AI systems on this instance: {total}")
        click.echo("This edition does not assign systems to organizations.")
    except Exception as exc:
        click.echo(f"Error: {exc}", err=True)
        sys.exit(1)
    finally:
        if db is not None:
            db.close()


if __name__ == "__main__":
    orphan_cleanup()
