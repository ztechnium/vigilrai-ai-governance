# Security Policy

VigilRAI Community Edition is a single-organization product, powered by [Ztechnium](https://ztechnium.com).

## Supported versions

| Version | Supported |
|---|---|
| 0.1.x (repository `main`) | Yes |

This repository is an alpha. Security reports are welcome. A fix in `main` is not a certification or a production-readiness claim.

## Reporting a vulnerability

Email [opensource@ztechnium.com](mailto:opensource@ztechnium.com). Please do not file a public GitHub issue for an unfixed vulnerability.

Include:

- What is affected (API, UI, SDK, or deployment default) and the version or commit
- Impact
- Steps to reproduce, or a proof of concept
- A suggested fix, if you have one

We aim to acknowledge reports within 3 business days.

## Deployment defaults

The Compose file and `.env.example` ship with local-only passwords (`rai_password`, `ChangeMe123!`, `dev-only-change-me`). They are for a private workstation. Replace them, set `ENVIRONMENT=production`, and set `ADMIN_BOOTSTRAP_ENABLED=false` before exposing a deployment. See [Deploy with Docker](docs/deployment/docker.md).

## Scope

This policy covers the control plane in this repository, including `packages/python-sdk` and `packages/typescript-sdk` as vendored here.

The published client repositories may also list their own contact path:

- Python SDK: [github.com/ztechnium/rai-python-sdk](https://github.com/ztechnium/rai-python-sdk)
- TypeScript SDK: [github.com/ztechnium/rai-typescript-sdk](https://github.com/ztechnium/rai-typescript-sdk)
