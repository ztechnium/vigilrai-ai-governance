# Contributing to rai-control-plane-sdk

> **DO NOT EDIT HERE.** Authoritative repository:
> [github.com/ztechnium/rai-python-sdk](https://github.com/ztechnium/rai-python-sdk)

Thank you for your interest in improving the RAI Control Plane Python SDK.

## Development Setup

```bash
git clone https://github.com/ztechnium/rai-python-sdk.git
cd rai-python-sdk
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
```

## Running Tests

Tests use mocked HTTP transports and do **not** require a live RAI Control Plane:

```bash
pytest
```

## Code Guidelines

- Preserve the stable `/sdk/v1` lifecycle contract (`start_session` → `observe_input` →
  `authorize_action` → `report_execution` → `observe_output` → `end`).
- Maintain fail-closed semantics: unreachable control plane must raise `RAIError`.
- Never log or expose API keys in reprs, error messages, or debug output.
- Keep the public import surface minimal: `from rai_sdk import RAIClient`.

## Pull Requests

1. Fork the public repository and create a feature branch.
2. Add or update tests for behavior changes.
3. Ensure `pytest`, `python -m build`, and `twine check dist/*` pass locally.
4. Open a PR with a clear description of the change and test plan.

## Releases

Releases are tagged `v*` on `ztechnium/rai-python-sdk` and published to PyPI via GitHub
Actions trusted publishing (OIDC).

## Questions

Open a [GitHub issue](https://github.com/ztechnium/rai-python-sdk/issues) or email
[opensource@ztechnium.com](mailto:opensource@ztechnium.com).
