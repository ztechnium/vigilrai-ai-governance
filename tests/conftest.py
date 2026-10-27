"""Pytest fixtures for integration testing."""

from __future__ import annotations

import hashlib
import os
import uuid
from pathlib import Path
from typing import Generator

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from rai_gateway.core.config import settings
from rai_gateway.core.database import get_db
from rai_gateway.main import app
from rai_gateway.models.database import (
    ApiKey,
    ExecutionAudit,
    Prompt,
    PromptAllowlist,
    PromptVersion,
)

pytest_plugins = [
    "approval_fixtures",
    "runtime_enforcement_fixtures",
]


def _build_test_engine_and_schema() -> tuple[str, str, object]:
    """Create a Postgres engine that uses a per-run isolated schema."""

    raw_url = os.environ.get("TEST_DATABASE_URL", settings.database_url)
    base_url = raw_url.split("?")[0]
    schema = f"test_{uuid.uuid4().hex}"

    base_engine = create_engine(base_url)
    with base_engine.connect() as conn:
        conn.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{schema}"'))
        conn.commit()

    schema_url = f"{base_url}?options=-csearch_path%3D{schema}"
    engine = create_engine(schema_url)
    return base_url, schema, engine


def _run_alembic_migrations(database_url: str) -> None:
    """Apply Alembic migrations to the given database URL."""
    root = Path(__file__).resolve().parents[1]
    alembic_cfg = Config(str(root / "alembic.ini"))
    alembic_cfg.set_main_option("sqlalchemy.url", database_url.replace("%", "%%"))
    previous = os.environ.get("TEST_DATABASE_URL")
    os.environ["TEST_DATABASE_URL"] = database_url
    try:
        command.upgrade(alembic_cfg, "head")
    finally:
        if previous is None:
            os.environ.pop("TEST_DATABASE_URL", None)
        else:
            os.environ["TEST_DATABASE_URL"] = previous


@pytest.fixture(scope="session")
def db_engine() -> Generator:
    """Session-scoped database engine with an isolated schema and Alembic migrations."""

    try:
        base_url, schema, engine = _build_test_engine_and_schema()
    except Exception as exc:
        pytest.fail(f"Database unavailable for integration tests: {exc}")

    schema_url = f"{base_url}?options=-csearch_path%3D{schema}"
    _run_alembic_migrations(schema_url)

    yield {"base_url": base_url, "schema": schema, "engine": engine}

    cleanup_engine = create_engine(base_url)
    with cleanup_engine.connect() as conn:
        conn.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        conn.commit()


@pytest.fixture()
def db_session(db_engine) -> Generator:
    """Provide a database session bound to the isolated schema."""

    session_local = sessionmaker(
        autocommit=False, autoflush=False, bind=db_engine["engine"]
    )
    db = session_local()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture()
def test_client(db_session, db_engine) -> Generator:
    """FastAPI TestClient with DB override and API key enforcement enabled."""

    def override_get_db() -> Generator:
        yield db_session

    original_require_api_key = settings.require_api_key
    settings.require_api_key = True

    app.dependency_overrides[get_db] = override_get_db

    import rai_gateway.core.health as health_module

    original_health_engine = health_module.engine
    health_module.engine = db_engine["engine"]

    client = TestClient(app)
    try:
        yield client
    finally:
        health_module.engine = original_health_engine
        settings.require_api_key = original_require_api_key
        app.dependency_overrides.pop(get_db, None)


@pytest.fixture()
def test_organization(db_session):
    """Singleton governance profile used by fixtures that used to create an org."""
    from rai_gateway.models.governance import OrganizationGovernanceProfile

    profile = (
        db_session.query(OrganizationGovernanceProfile)
        .filter(OrganizationGovernanceProfile.singleton_key == "default")
        .first()
    )
    if profile is None:
        profile = OrganizationGovernanceProfile(
            singleton_key="default",
            name="Test Organization",
            legal_name="Test Organization",
            organization_type="PRIVATE_ENTERPRISE",
            pilot_status="PLANNING",
            updated_by="tester",
        )
        db_session.add(profile)
        db_session.commit()
        db_session.refresh(profile)
    return profile


@pytest.fixture()
def api_key_header(db_session) -> dict[str, str]:
    """Insert an active API key and return request headers."""

    plaintext = "test-api-key"
    key_hash = hashlib.sha256(plaintext.encode("utf-8")).hexdigest()

    db_session.query(ApiKey).delete()
    db_session.add(
        ApiKey(
            key_hash=key_hash,
            system_id="test_system",
            scopes=["execute"],
            status="active",
        )
    )
    db_session.commit()

    return {"X-API-Key": plaintext}


@pytest.fixture()
def seed_prompt(db_session) -> dict[str, str]:
    """Seed a minimal prompt, version, and allowlist entry."""

    prompt_id = "test_prompt"
    # Ensure idempotent seeding across tests in the same session.
    db_session.query(ExecutionAudit).filter(
        ExecutionAudit.prompt_id == prompt_id
    ).delete()
    db_session.query(PromptAllowlist).filter(
        PromptAllowlist.prompt_id == prompt_id
    ).delete()
    db_session.query(PromptVersion).filter(
        PromptVersion.prompt_id == prompt_id
    ).delete()
    db_session.query(Prompt).filter(Prompt.prompt_id == prompt_id).delete()
    db_session.commit()

    db_session.add(
        Prompt(
            prompt_id=prompt_id,
            name="Test Prompt",
            domain="testing",
            description="Integration test prompt",
            status="active",
            owner_system_id="test_system",
        )
    )
    db_session.add(
        PromptVersion(
            prompt_id=prompt_id,
            version=1,
            status="active",
            template="Hello {name}",
            required_vars_schema={
                "type": "object",
                "properties": {"name": {"type": "string"}},
            },
            expected_output_schema=None,
            model_policy={"provider": "openai"},
            policy_version="v1",
            created_by="tester",
        )
    )
    db_session.add(
        PromptAllowlist(
            prompt_id=prompt_id,
            version=1,
            system_id="test_system",
            module="test_module",
            allowed=True,
        )
    )
    db_session.commit()

    return {"prompt_id": prompt_id, "version": 1}


@pytest.fixture()
def mock_llm_provider(monkeypatch):
    """Mock LLM provider to avoid external calls during tests."""

    class _MockProvider:
        async def generate(self, prompt: str, variables: dict, model: str, **kwargs):
            return {
                "output": "mock-output",
                "model": model,
                "usage": {"prompt_tokens": 5, "completion_tokens": 5},
                "provider": "mock",
            }

    def _get_provider(_provider_name: str = "openai"):
        return _MockProvider()

    monkeypatch.setattr(
        "rai_gateway.services.llm_controller.get_llm_provider",
        _get_provider,
    )

    return _MockProvider()
