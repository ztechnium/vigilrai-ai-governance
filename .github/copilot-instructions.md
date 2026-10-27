# Copilot instructions for the VigilRAI community edition

## Product

VigilRAI Community Edition is a single-organization AI governance console, powered by Ztechnium. It is not a multi-organization service. Do not add company registration, an organization switcher, or `X-Organization-ID`.

Read these files before making architectural changes:

1. `README.md`
2. `docs/releases/SYSTEM_STATUS.md`
3. `docs/DOCUMENTATION_INDEX.md`
4. `docs/operations/TENANT_OWNERSHIP_MAP.md`

Canonical documents override historical plans and point-in-time validation reports.

## Architecture Responsibilities

### RAI Control Plane owns

- Versioned AI-system and agent registry
- Ownership, accountability, risk, controls, and residual-risk acceptance
- Governance and deployment lifecycle
- Durable human approval workflow
- Regulatory obligations and evidence requirements
- Runtime policy distribution and normalized receipt ingestion
- Cases, incidents, dashboards, assurance, and regulator reporting

### Runtime enforcement provider owns

- Authenticated agent and delegation identity
- Pre-action policy enforcement
- Tool, MCP, API, database, network, and agent-to-agent mediation
- Sandboxing, budgets, circuit breakers, and kill switches
- Action-bound approval consumption
- Decision receipts, traces, and security events

Do not duplicate AGT runtime capabilities in custom code unless an explicit gap and
adapter-independent requirement are documented.

## Critical Trust Rules

- Never trust caller-supplied risk level, effective permissions, allowlists, approval
  state, or deployment state. Resolve them from approved server-side records.
- Every controlled side effect must pass through an enforcement point before execution.
- Prompt instructions are not authorization controls.
- High-risk approval must be identity-backed, qualified, action-bound, parameter-bound,
  expiring, one-time, and durably recorded.
- Fail closed on policy, identity, approval, catalogue, guard, or integrity failures.
- Do not store raw secrets or hidden chain-of-thought. Store normalized decision
  evidence, safe summaries, hashes, identifiers, policy versions, and receipts.
- Material changes to model, prompt, workflow, tool, MCP server, permission, data,
  autonomy, vendor, or regulation must trigger re-risking and retesting.

## Existing LLM Gateway Invariants

- Runtime calls reference approved `prompt_id + version`.
- System/module allowlists are checked before generation.
- Responsible-AI checks run before and after model invocation.
- Critical guard/catalogue failures are fail-closed.
- Sensitive payloads are not written to audit logs.
- Trace identifiers propagate through execution and evidence.

`/v1/execute` is the LLM prompt module. Tool and MCP actions go through the runtime
enforcement API. Do not treat a prompt-guard result as authorization for a tool call.

## Where the implementation lives

Registry, identity, approval, policy, runtime enforcement, evidence, risk intelligence,
evaluations, governance, portfolio reporting, and `/sdk/v1` already have packages under
`src/rai_gateway/`. Read [Current status](docs/releases/SYSTEM_STATUS.md) before adding
a parallel implementation. Do not recreate removed demo seeders or agent execution plans.

## Definition of Done

A control is not complete until it has:

- an authoritative data owner and lifecycle;
- API/service enforcement;
- positive, negative, authorization, and failure-path tests;
- audit or decision evidence;
- migration and rollback behavior where data changes;
- documentation that labels actual maturity accurately.

For tool enforcement, tests must prove denied actions never invoke the underlying tool.
For approvals, tests must cover replay, expiry, tampering, self-approval, wrong role,
unavailable infrastructure, and concurrent consumption.

## Documentation Rules

- Use `implemented`, `partially implemented`, `planned`, `operational evidence
  required`, or `historical` consistently.
- Never claim certification, compliance, production readiness, uptime, immutability,
  or complete framework coverage without dated objective evidence and authority.
- Update `docs/releases/SYSTEM_STATUS.md` when implementation maturity changes.
- Keep aspirational design separate from current state.
- Preserve historical documents as records, but add a superseded notice when needed.

## Security and Quality

- Use least privilege and deny by default for unknown agent actions.
- Keep secrets in an approved secret manager; never commit `.env` or credentials.
- Use OpenTelemetry-compatible traces and normalized metadata.
- Keep one instance. Authorize product APIs from memberships, not from an organization header.
- Prefer migrations to runtime `create_all()` in controlled deployments.
- Treat skipped database or integration tests as unresolved evidence, not success.
