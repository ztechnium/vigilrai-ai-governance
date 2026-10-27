# VigilRAI Community Edition — current status

**Status:** Canonical

**Last reviewed:** 2026-10-27

**Product stage:** Alpha

**Powered by:** [Ztechnium](https://ztechnium.com)

This page records what this single-organization edition implements. It is not a production-readiness or certification statement.

## Summary

The control plane can register AI systems and agents, issue runtime identity, evaluate policy, require human approval, authorize or deny actions before they run, and store trajectory and oversight records. A Next.js UI, PostgreSQL migrations, Docker Compose, and Python and TypeScript SDKs ship with the service.

A new install starts with default roles, one governance profile, and the bootstrap admin in `.env.example`. Sample MCP templates are optional (`make seed-mcp-catalog`). This edition does not register companies and does not seed multiple organizations.

No certification has been granted. Words such as certified, compliant, or production-ready are not claims of this edition.

## Implemented areas

| Area | What this edition ships |
|---|---|
| Engineering baseline | Alembic migrations, GitHub Actions CI, Ruff, mypy on core modules, pytest, Vitest, Playwright smoke |
| Registry | AI systems, agents, immutable versions, dependencies, resource catalog |
| Identity | Runtime identities and credentials |
| Policy | Policy library and RAI rules |
| Approval | Action-bound human approval before a held action runs |
| Runtime enforcement | Authorize or deny a tool, MCP, or model action before it runs, with decision receipts |
| Evidence | Trajectories and the runtime audit explorer. A client `conversation_id` can still be stored on a trajectory. There is no Conversations page |
| Risk | Overview, budgets, findings, monitoring, emergency controls, and content evaluation |
| FinOps | Usage overview for this instance |
| Reporting | Operational reports and one portfolio overview |
| Team | One company profile, departments, membership roles, and platform users and roles on Team & roles |
| Product surface | Sign-in at `/`, `/sdk/v1`, webhooks, API keys, Python SDK, TypeScript SDK |
| LLM prompt module | `POST /v1/execute`. Observed prompts open in Trajectories |

The console sidebar is Dashboard, Reports, Onboarding, AI Systems, Resource Catalog, Policy Library, RAI Rules, Runtime Identities, Trajectories, Approvals, Audit Explorer, Risk, FinOps, Portfolio overview, Team & roles, API Keys, Settings, and Webhooks.

These areas have application code. Operational evidence — backups, an identity provider, and uptime — is still required before any production claim. See [backup and restore](../operations/BACKUP_RESTORE_DR.md).

## Not in this edition

- A public marketing site, company registration, or an organization switcher
- More than one organization, `organization_id`, or the `X-Organization-ID` header
- Conversations list and detail pages
- Console pages that were marked “soon”: test console, anomalies, interventions, recommendations, evaluation suites and runs, deployment gates and waivers, controls, reviews, incidents, exceptions, evidence packages, due work, and the portfolio drill-down pages
- Audit logs, compliance reports, feature flags, and the pilot dashboard

Some of those still have backend modules. They are not part of the community console.

## Explicitly out of scope for this status page

- Regulatory certification or a completed assurance evidence pack
- A claim that Microsoft Agent Governance Toolkit is bundled or required at runtime
- Live availability of any hosted environment

## How to verify

```bash
docker compose up --build
curl -fsS http://localhost:8001/health
curl -fsS http://localhost:8001/ready
```

Backend tests need PostgreSQL. See [DEVELOPMENT.md](../../DEVELOPMENT.md).
