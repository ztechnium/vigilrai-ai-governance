"""MCP endpoint host allowlist / private-network policy."""

from __future__ import annotations

from rai_gateway.core.config import settings
from rai_gateway.runtime_enforcement.adapters.mcp import MCPToolExecutionAdapter


def test_mcp_rejects_http_in_production(db_session, monkeypatch):
    monkeypatch.setattr(settings, "mcp_allow_http", False)
    monkeypatch.setattr(settings, "mcp_allow_private_hosts", True)
    monkeypatch.setattr(settings, "mcp_allowed_hosts", None)
    adapter = MCPToolExecutionAdapter(db_session, adapter_mode="PRODUCTION")
    err = adapter._validate_endpoint("http://tools.example.com/invoke")
    assert err is not None
    assert "https" in err.lower()


def test_mcp_rejects_private_ip(db_session, monkeypatch):
    monkeypatch.setattr(settings, "mcp_allow_http", False)
    monkeypatch.setattr(settings, "mcp_allow_private_hosts", False)
    monkeypatch.setattr(settings, "mcp_allowed_hosts", None)
    adapter = MCPToolExecutionAdapter(db_session, adapter_mode="PRODUCTION")
    err = adapter._validate_endpoint("https://10.0.0.5/mcp")
    assert err is not None
    assert "private" in err.lower()


def test_mcp_rejects_localhost(db_session, monkeypatch):
    monkeypatch.setattr(settings, "mcp_allow_private_hosts", False)
    adapter = MCPToolExecutionAdapter(db_session, adapter_mode="PRODUCTION")
    err = adapter._validate_endpoint("https://localhost/mcp")
    assert err is not None
    assert "private" in err.lower() or "local" in err.lower()


def test_mcp_host_allowlist(db_session, monkeypatch):
    monkeypatch.setattr(settings, "mcp_allow_http", False)
    monkeypatch.setattr(settings, "mcp_allow_private_hosts", True)
    monkeypatch.setattr(
        settings, "mcp_allowed_hosts", "tools.example.com,*.partner.example"
    )
    adapter = MCPToolExecutionAdapter(db_session, adapter_mode="PRODUCTION")

    assert adapter._validate_endpoint("https://tools.example.com/invoke") is None
    assert adapter._validate_endpoint("https://east.partner.example/invoke") is None
    err = adapter._validate_endpoint("https://evil.other.com/invoke")
    assert err is not None
    assert "allowlist" in err.lower()


def test_mcp_private_allowed_when_flag_set(db_session, monkeypatch):
    monkeypatch.setattr(settings, "mcp_allow_http", True)
    monkeypatch.setattr(settings, "mcp_allow_private_hosts", True)
    monkeypatch.setattr(settings, "mcp_allowed_hosts", None)
    adapter = MCPToolExecutionAdapter(db_session, adapter_mode="PRODUCTION")
    assert adapter._validate_endpoint("http://10.0.0.5/mcp") is None
