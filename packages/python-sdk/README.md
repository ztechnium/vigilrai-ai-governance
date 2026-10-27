# RAI Control Plane Python SDK

Official Python client for the RAI Control Plane stable `/sdk/v1` governance API.

**Never execute a consequential side effect before RAI returns ALLOW.**

## Requirements

- Python **3.10** or newer (3.10–3.13 supported in CI)
- A RAI Control Plane deployment and runtime agent credentials

## Installation

```bash
pip install rai-control-plane-sdk
```

## Minimal usage

```python
from rai_sdk import RAIClient

client = RAIClient(
    base_url="https://rai.example.com",
    api_key="rai_...",
    integration_id="...",
)

client.heartbeat()

session = client.start_session(
    external_session_id="session-001",
    channel="application",
)

session.observe_input("Create an order")

decision = session.authorize_action(
    tool="create_order",
    parameters={
        "amount": 100,
        "currency": "USD",
    },
)

if decision.allowed:
    # Execute the application's side effect here.
    decision.report_execution(
        client,
        status="SUCCEEDED",
    )

session.end()
client.close()
```

Or use a context manager:

```python
with RAIClient(base_url="...", api_key="...", integration_id="...") as client:
    client.heartbeat()
```

## Authorization decisions

`authorize_action` returns a `Decision`. Check `decision.decision` (or `decision.allowed`
for the ALLOW case):

| Decision | Meaning | Application action |
| -------- | ------- | ------------------ |
| `ALLOW` | Action is permitted | Execute the side effect, then call `report_execution` |
| `DENY` | Action is blocked | Do **not** execute; surface `human_message` / `reason_code` as needed |
| `REQUIRE_APPROVAL` | Human approval required | Do **not** execute until approved; use `approval_request_id` |
| `MONITOR` | Observed / audited without blocking | Follow your product policy; still do not treat as unconditional ALLOW unless `decision.allowed` is true |

Only `decision.allowed` (`decision == "ALLOW"`) means it is safe to perform a
consequential side effect.

## Fail-closed behavior

By default (`fail_closed=True`), network errors, timeouts, and unreachable control-plane
endpoints raise `RAIError` with code `RAI_UNAVAILABLE`. Treat the control plane as
unavailable and **do not** execute consequential side effects — retry or abort according
to your integration policy.

HTTP error responses from the control plane (4xx/5xx with a structured body) raise
`RAIError` with the server-provided error code and message.

## Idempotency

`authorize_action` accepts an optional `idempotency_key`. When supplied, the SDK sends
it as both the JSON `idempotency_key` field and the `Idempotency-Key` HTTP header so
retries of the same authorization request can be safely deduplicated by the server.

If you omit `idempotency_key`, the SDK generates a unique key for the JSON body only
(no `Idempotency-Key` header).

## Runtime credentials

Construct `RAIClient` with:

- `base_url` — your RAI Control Plane base URL
- `api_key` — runtime agent key (sent as `X-RAI-Agent-Key`)
- `integration_id` — integration identifier for heartbeat and sessions

Store secrets in environment variables or a secrets manager. Never commit API keys.
`RAIClient.__repr__` never includes the API key; error messages redact it when echoed.

## Session lifecycle

```text
heartbeat / health
  → start_session
  → observe_input
  → authorize_action   (ALLOW | DENY | REQUIRE_APPROVAL | MONITOR)
  → report_execution   (after ALLOW, when a side effect runs)
  → authorize_data_access / record_usage   (optional)
  → observe_output
  → end_session
```

### Metering

```python
session.record_model_call(
    provider="openai",
    model="gpt-4o",
    input_tokens=120,
    output_tokens=40,
)
```

Helpers `usage_from_openai`, `usage_from_anthropic`, and `usage_from_gemini` extract
token fields from common provider response shapes.

### Data access

```python
session.authorize_data_access(
    resource="customer.profile",
    fields=["email", "ssn"],
    purpose="support_summary",
)
```

### Approvals

When `authorize_action` returns `REQUIRE_APPROVAL`, poll with
`client.get_approval_status(decision.approval_request_id)`.

## API compatibility

This SDK targets the stable `/sdk/v1` HTTP contract (`API_RANGE = ">=1.0.0,<2.0.0"`).
Your control-plane deployment must expose compatible `/sdk/v1` endpoints.

Pass `delegation_id` on `start_session` to bind a grant for this instance. Ended sessions
are not reused unless `allow_ended_session_reuse=True`.

## Error handling

```python
from rai_sdk import RAIClient, RAIError

try:
    client.heartbeat()
except RAIError as exc:
    # exc.code, exc.message, exc.retryable, exc.status_code, exc.details
    if exc.code == "RAI_UNAVAILABLE":
        # Fail closed: do not execute side effects
        raise
```

## Async client

`AsyncRAIClient` is **not included in 0.2.0**. Async support is deferred to a future
release. For asyncio applications today, run the synchronous `RAIClient` in a thread pool
(`asyncio.to_thread`) or call the REST API directly.

## Development

See [CONTRIBUTING.md](CONTRIBUTING.md).

```bash
pip install -e ".[dev]"
pytest
python -m build
twine check dist/*
```

## Links

- [Repository](https://github.com/ztechnium/rai-python-sdk)
- [Changelog](CHANGELOG.md)
- [Security policy](SECURITY.md)

## License

Apache-2.0 — see [LICENSE](LICENSE).
