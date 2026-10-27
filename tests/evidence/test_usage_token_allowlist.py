"""Usage metrics must not be redacted as secrets when keys contain 'token'."""

from rai_gateway.evidence.redaction import redact_secrets
from rai_gateway.runtime_enforcement.service import _redact_parameters


def test_usage_token_fields_are_not_redacted():
    payload = {
        "estimated_input_tokens": 1200,
        "input_tokens": 1180,
        "estimated_output_tokens": 400,
        "output_tokens": 380,
        "token_usage": 1560,
        "total_tokens": 1560,
        "prompt_tokens": 1180,
        "completion_tokens": 380,
        "max_tokens": 4096,
        "access_token": "secret-should-go",
        "api_token": "also-secret",
    }
    scrubbed = redact_secrets(payload)
    assert scrubbed["estimated_input_tokens"] == 1200
    assert scrubbed["input_tokens"] == 1180
    assert scrubbed["estimated_output_tokens"] == 400
    assert scrubbed["output_tokens"] == 380
    assert scrubbed["token_usage"] == 1560
    assert scrubbed["total_tokens"] == 1560
    assert scrubbed["prompt_tokens"] == 1180
    assert scrubbed["completion_tokens"] == 380
    assert scrubbed["max_tokens"] == 4096
    assert scrubbed["access_token"] == "[REDACTED]"
    assert scrubbed["api_token"] == "[REDACTED]"


def test_execution_report_keeps_usage_tokens_and_cost():
    """FinOps usage rides on the execution report. Cost has no 'token' in the
    key, so it survived; token counts were wiped and the UI showed 0."""
    report = _redact_parameters(
        {
            "usage": {
                "prompt_tokens": 1180,
                "completion_tokens": 380,
                "total_tokens": 1560,
                "cached_input_tokens": 40,
                "reasoning_tokens": 12,
            },
            "cost": {"amount": 0.0041, "currency": "USD"},
            "access_token": "secret-should-go",
        }
    )
    assert report["usage"]["prompt_tokens"] == 1180
    assert report["usage"]["completion_tokens"] == 380
    assert report["usage"]["total_tokens"] == 1560
    assert report["usage"]["cached_input_tokens"] == 40
    assert report["usage"]["reasoning_tokens"] == 12
    assert report["cost"]["amount"] == 0.0041
    assert report["access_token"] == "[REDACTED]"
