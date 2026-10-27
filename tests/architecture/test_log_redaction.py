"""Tests proving sensitive values are not emitted in structured audit logs."""

from __future__ import annotations

import io
import json
import logging

from rai_gateway.core.observability import log_execution_audit


def test_sensitive_values_redacted_from_execution_audit_logs():
    """Structured audit logs must not contain raw secret field values."""
    log_capture = io.StringIO()
    handler = logging.StreamHandler(log_capture)
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(logging.INFO)

    secret_value = "sk-test-secret-api-key-12345"
    log_execution_audit(
        trace_id="trace-1",
        execution_id="exec-1",
        prompt_id="p1",
        prompt_version=1,
        system_id="sys1",
        decision="allow",
        api_key=secret_value,
        password=secret_value,
        authorization_header=f"Bearer {secret_value}",
    )

    output = log_capture.getvalue()
    assert secret_value not in output
    assert "REDACTED" in output or "[REDACTED]" in output

    # Verify JSON structure is still valid and metadata is present
    for line in output.strip().splitlines():
        if line.strip():
            parsed = json.loads(line)
            assert parsed.get("event") == "execution_audit"
            assert parsed.get("prompt_id") == "p1"
