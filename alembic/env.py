"""Alembic environment configuration.

This project currently uses SQLAlchemy models in `rai_gateway.models.database`.
Even if you choose to rely on `Base.metadata.create_all()` during early
development, having a working Alembic environment prevents `alembic upgrade`
from failing and enables future migrations.
"""

from __future__ import annotations

import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

import rai_gateway.models.approval  # noqa: F401
import rai_gateway.models.auth  # noqa: F401 — SaaS auth sessions
import rai_gateway.models.client_hooks  # noqa: F401
import rai_gateway.models.data_access  # noqa: F401 — Phase 2 data access
import rai_gateway.models.evaluations  # noqa: F401 — WP7
import rai_gateway.models.evidence  # noqa: F401
import rai_gateway.models.finops  # noqa: F401 — FinOps pricing/reservation
import rai_gateway.models.governance  # noqa: F401 — organizations FK for AI systems
import rai_gateway.models.identity  # noqa: F401
import rai_gateway.models.lineage  # noqa: F401
import rai_gateway.models.metering  # noqa: F401 — runtime metering spans
import rai_gateway.models.policy_engine  # noqa: F401 — policy engine tables
import rai_gateway.models.policy_library  # noqa: F401 — Policy Library sources
import rai_gateway.models.portfolio  # noqa: F401
import rai_gateway.models.productization  # noqa: F401
import rai_gateway.models.registry  # noqa: F401 — WP1 registry tables
import rai_gateway.models.risk_intelligence  # noqa: F401 — WP6
import rai_gateway.models.runtime_enforcement  # noqa: F401
from rai_gateway.core.config import settings
from rai_gateway.models.database import Base

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Tests set TEST_DATABASE_URL to an isolated schema. Honor it ahead of the
# process DATABASE_URL so migrations do not land on the shared public schema.
explicit_url = os.environ.get("TEST_DATABASE_URL") or os.environ.get("DATABASE_URL")
if explicit_url:
    config.set_main_option("sqlalchemy.url", explicit_url.replace("%", "%%"))
elif settings.database_url:
    config.set_main_option("sqlalchemy.url", settings.database_url)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section) or {},
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
