"""Unified RAI Rules query and Policy Library tests."""

from __future__ import annotations

import uuid

from rai_gateway.policy.library import PolicyLibraryService
from rai_gateway.policy.rule_query import RaiRulesQueryService
from rai_gateway.policy.service import PolicyCollectionService


def test_unified_rules_query_content_and_tool(
    policy_stack, db_session, test_organization
):
    svc = PolicyCollectionService(db_session)
    system_id = policy_stack["system"].id
    svc.create_content_rule(
        system_id,
        title="Never expose banking information",
        content="Do not disclose bank accounts",
        effect="DENY",
        applies_to="OUTPUT",
        severity="CRITICAL",
        category="PRIVACY",
        actor="tester",
    )
    svc.create_tool_rule(
        system_id,
        title="High value refund",
        tool_id=policy_stack["tool"].id,
        mcp_server_id=policy_stack["mcp"].id,
        effect="REQUIRE_APPROVAL",
        required_approver_role="business_approver",
        severity="HIGH",
        category="FINANCIAL",
        actor="tester",
    )

    query = RaiRulesQueryService(db_session)
    all_rules = query.query(limit=200)
    types = {i["rule_type"] for i in all_rules["items"]}
    assert "CONTENT" in types
    assert "TOOL" in types
    assert all_rules["total"] >= 2

    content_only = query.query(rule_type="CONTENT", limit=200)
    assert all(i["rule_type"] == "CONTENT" for i in content_only["items"])

    by_system = query.query(
        ai_system_id=system_id,
        limit=200,
    )
    assert by_system["total"] >= 2

    by_tool = query.query(
        tool_id=policy_stack["tool"].id,
        limit=200,
    )
    assert by_tool["total"] >= 1
    assert all(i["rule_type"] == "TOOL" for i in by_tool["items"])


def test_policy_library_manual_text_and_link(
    policy_stack, db_session, test_organization
):
    library = PolicyLibraryService(db_session)
    source = library.create_source(
        title="Information Security Policy v3",
        source_type="MANUAL_TEXT",
        authority="ZTechnium",
        jurisdiction="EG",
        policy_type="internal",
        version="v3",
        content_text="Never disclose customer banking information. Section 7.2.",
        actor="tester",
    )
    assert source["content_digest"]
    assert source["source_type"] == "MANUAL_TEXT"
    assert source["ingestion_status"] == "READY"

    listed = library.list_sources()
    assert listed["total"] >= 1
    assert any(i["id"] == source["id"] for i in listed["items"])

    detail = library.get_source(uuid.UUID(source["id"]))
    assert len(detail["obligations"]) >= 1

    svc = PolicyCollectionService(db_session)
    rule = svc.create_content_rule(
        policy_stack["system"].id,
        title="Never expose banking information",
        content="Do not disclose bank accounts",
        effect="DENY",
        actor="tester",
    )
    link = library.link_rule(
        policy_source_id=uuid.UUID(source["id"]),
        rule_type="CONTENT",
        rule_id=rule.id,
        obligation_id=uuid.UUID(detail["obligations"][0]["id"]),
    )
    assert link["rule_type"] == "CONTENT"

    query = RaiRulesQueryService(db_session)
    linked = query.query(
        source_policy_id=source["id"],
        limit=50,
    )
    assert linked["total"] >= 1
    assert linked["items"][0]["source_policy"]["title"] == source["title"]


def test_policy_library_url_source_metadata(db_session, test_organization):
    library = PolicyLibraryService(db_session)
    source = library.create_source(
        title="EU AI Act",
        source_type="URL",
        authority="EU",
        source_uri="https://company.example/policies/privacy",
        actor="tester",
    )
    assert source["source_uri"] == "https://company.example/policies/privacy"
    assert source["crawl_metadata"]["source_url"] == source["source_uri"]
    assert source["crawl_metadata"]["crawl_scope"] == "SINGLE_URL"
