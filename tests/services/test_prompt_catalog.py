"""Prompt catalog service tests."""

import pytest

from rai_gateway.services.prompt_catalog import PromptCatalogService


@pytest.mark.asyncio
async def test_resolve_prompt_returns_config(db_session, seed_prompt):
    service = PromptCatalogService(db_session)

    config = await service.resolve_prompt(
        seed_prompt["prompt_id"],
        seed_prompt["version"],
        trace_id="test-trace",
    )

    assert config is not None
    assert config["prompt_id"] == seed_prompt["prompt_id"]
    assert config["template"] == "Hello {name}"


@pytest.mark.asyncio
async def test_check_allowlist_returns_true(db_session, seed_prompt):
    service = PromptCatalogService(db_session)

    allowed = await service.check_allowlist(
        seed_prompt["prompt_id"],
        seed_prompt["version"],
        system_id="test_system",
        module="test_module",
        trace_id="test-trace",
    )

    assert allowed is True


@pytest.mark.asyncio
async def test_check_allowlist_returns_false(db_session, seed_prompt):
    service = PromptCatalogService(db_session)

    allowed = await service.check_allowlist(
        seed_prompt["prompt_id"],
        seed_prompt["version"],
        system_id="test_system",
        module="wrong_module",
        trace_id="test-trace",
    )

    assert allowed is False
