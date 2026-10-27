"""Platform Policy Library seed."""

from __future__ import annotations

from rai_gateway.models.policy_library import PolicySource, PolicySourceObligation
from rai_gateway.policy.library import PolicyLibraryService
from rai_gateway.policy.seed_library import (
    DEFAULT_SEED_PATH,
    PolicyLibrarySeedService,
    load_policy_seed,
)


def test_policy_seed_file_has_pii_and_gdpr() -> None:
    catalog = load_policy_seed(DEFAULT_SEED_PATH)
    keys = {item["source_key"] for item in catalog["policies"]}
    assert keys == {"pii", "gdpr"}


def test_seed_is_visible_to_any_organization(db_session, test_organization) -> None:
    result = PolicyLibrarySeedService(db_session).seed(DEFAULT_SEED_PATH)
    assert result.sources_created == 2
    again = PolicyLibrarySeedService(db_session).seed(DEFAULT_SEED_PATH)
    assert again.sources_created == 0
    assert again.sources_updated == 2

    listed = PolicyLibraryService(db_session).list_sources()
    titles = {item["title"] for item in listed["items"]}
    assert "Personal data (PII)" in titles
    assert "GDPR personal data" in titles
    platform = [item for item in listed["items"] if item["scope"] == "PLATFORM"]
    assert len(platform) == 2

    source = (
        db_session.query(PolicySource).filter(PolicySource.source_key == "pii").one()
    )
    obligations = (
        db_session.query(PolicySourceObligation)
        .filter(PolicySourceObligation.policy_source_id == source.id)
        .all()
    )
    assert {row.section_ref for row in obligations} == {"pii-1", "pii-2", "pii-3"}
