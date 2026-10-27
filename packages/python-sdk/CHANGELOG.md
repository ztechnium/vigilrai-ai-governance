# Changelog

All notable changes to `rai-control-plane-sdk` are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.2.0] - 2026-09-26

### Added

- `Session.record_usage` / `record_model_call` / `report_model_usage` → `POST .../metering/spans`
- `Session.complete_metering_span` → `PATCH .../metering/spans/{span_id}`
- `Session.authorize_data_access` → `POST .../data-access/authorize`
- `RAIClient.get_approval_status` → `GET /sdk/v1/approvals/{id}`
- `start_session` options: `delegation_id`, `allow_ended_session_reuse`
- `ConfigurationProvenanceMetadata` typing for session/input/output metadata
- Provider helpers: `usage_from_openai`, `usage_from_anthropic`, `usage_from_gemini`

### Changed

- Package version bumped to `0.2.0` (additive `/sdk/v1` surface; no breaking changes to core lifecycle)

## [0.1.0] - 2026-03-24

### Added

- Initial public POC of the official Python SDK for RAI Control Plane `/sdk/v1`.
- `RAIClient` with fail-closed semantics for network and control-plane failures.
- Session lifecycle helpers: `start_session`, `observe_input`, `authorize_action`,
  `report_execution`, `observe_output`, `end`.
- Operational endpoints: `health`, `heartbeat`, `get_decision`.
- Typed package marker (`py.typed`) for PEP 561 consumers.
- Unit tests with mocked HTTP transport (no live server required).

### Notes

- Async client (`AsyncRAIClient`) is deferred to a future release; see README.

[0.2.0]: https://github.com/ztechnium/rai-python-sdk/releases/tag/v0.2.0
[0.1.0]: https://github.com/ztechnium/rai-python-sdk/releases/tag/v0.1.0
