"""Alembic migration tests."""

from __future__ import annotations

import os
import uuid
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text

PROJECT_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture()
def fresh_migration_db():
    """Create an isolated schema and yield its connection URL."""
    raw_url = os.environ.get(
        "TEST_DATABASE_URL",
        "postgresql://rai_user:rai_password@localhost:5434/rai_gateway",
    )
    base_url = raw_url.split("?")[0]
    schema = f"migrate_test_{uuid.uuid4().hex}"

    base_engine = create_engine(base_url)
    with base_engine.connect() as conn:
        conn.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{schema}"'))
        conn.commit()

    schema_url = f"{base_url}?options=-csearch_path%3D{schema}"
    yield schema_url

    with base_engine.connect() as conn:
        conn.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        conn.commit()
    base_engine.dispose()


def _configure_alembic(cfg: Config, database_url: str) -> None:
    cfg.set_main_option("sqlalchemy.url", database_url.replace("%", "%%"))
    os.environ["TEST_DATABASE_URL"] = database_url


def test_empty_db_upgrade_head(fresh_migration_db):
    """Fresh empty database can migrate to head via Alembic only."""
    cfg = Config(str(PROJECT_ROOT / "alembic.ini"))
    _configure_alembic(cfg, fresh_migration_db)

    command.upgrade(cfg, "head")

    engine = create_engine(fresh_migration_db)
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    engine.dispose()

    expected = {"prompts", "prompt_versions", "api_keys", "executions_audit"}
    assert expected.issubset(tables)


def test_migration_downgrade_base(fresh_migration_db):
    """The single-organization migration cannot be reversed."""
    cfg = Config(str(PROJECT_ROOT / "alembic.ini"))
    _configure_alembic(cfg, fresh_migration_db)

    command.upgrade(cfg, "head")
    with pytest.raises(RuntimeError, match="cannot be reversed"):
        command.downgrade(cfg, "base")
