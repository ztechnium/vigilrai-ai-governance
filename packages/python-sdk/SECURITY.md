# Security Policy

## Supported Versions

| Version | Supported          |
| ------- | ------------------ |
| 0.1.x   | :white_check_mark: |

## Reporting a Vulnerability

If you discover a security issue in the RAI Control Plane Python SDK, please report it
responsibly rather than opening a public GitHub issue.

**Email:** [opensource@ztechnium.com](mailto:opensource@ztechnium.com)

Include:

- A description of the vulnerability and its potential impact
- Steps to reproduce or a proof of concept
- Affected SDK version(s)
- Any suggested remediation, if available

We aim to acknowledge reports within **3 business days** and will coordinate disclosure
once a fix is available.

## Scope

This policy covers the `rai-control-plane-sdk` client library published from
[github.com/ztechnium/rai-python-sdk](https://github.com/ztechnium/rai-python-sdk).

Server-side vulnerabilities in the RAI Control Plane product should be reported to the
same contact ([opensource@ztechnium.com](mailto:opensource@ztechnium.com)).

## SDK Security Practices

- **Fail-closed by default:** network and control-plane failures raise `RAIError` with
  code `RAI_UNAVAILABLE` so integrators must not execute consequential side effects.
- **Credential handling:** API keys are sent via the `X-RAI-Agent-Key` header and are
  never included in `RAIClient.__repr__` or redacted when echoed in error messages.
- **Do not commit secrets:** store agent keys in environment variables or a secrets
  manager, not in source control.
