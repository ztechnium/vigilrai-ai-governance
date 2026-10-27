# @ztechnium/rai-sdk

> **DO NOT EDIT HERE.** This directory is a temporary mirror.
> Authoritative repository: [github.com/ztechnium/rai-typescript-sdk](https://github.com/ztechnium/rai-typescript-sdk)

Official TypeScript/Node.js SDK for the RAI Control Plane stable `/sdk/v1` governance API.

## Install

```bash
npm install @ztechnium/rai-sdk
```

Requires Node.js 18 or later.

## Quickstart

```typescript
import { RAIClient } from "@ztechnium/rai-sdk";

const client = new RAIClient({
  baseUrl: process.env.RAI_BASE_URL!,
  apiKey: process.env.RAI_AGENT_KEY!,
  integrationId: process.env.RAI_INTEGRATION_ID!,
});

await client.heartbeat();

const session = await client.startSession({
  channel: "application",
});

await session.observeInput({
  content: "Create an order",
});

const decision = await session.authorizeAction({
  tool: "create_order",
  parameters: {
    amount: 100,
    currency: "USD",
  },
});

if (decision.allowed) {
  // Execute application's side effect.
  await decision.reportExecution(client, {
    status: "SUCCEEDED",
  });
}

await session.end();
```

**Never execute a consequential side effect before RAI returns `ALLOW`.**

## Session lifecycle

Typical flow:

1. `heartbeat` — register SDK version and capability matrix
2. `startSession` — open a governed session
3. `observeInput` — record user/application input
4. `authorizeAction` — request a policy decision before side effects
5. execute only when `decision.allowed` is true, then `reportExecution`
6. `observeOutput` — record model/application output (optional)
7. `recordUsage` / `recordModelCall` — report token/cost metering (optional)
8. `authorizeDataAccess` — authorize/mask structured data before model use (optional)
9. `end` — close the session

## Authorization decisions

| Decision | `decision.allowed` | Meaning |
| --- | --- | --- |
| `ALLOW` | `true` | Proceed with the side effect, then report execution |
| `DENY` | `false` | Do not execute the side effect |
| `REQUIRE_APPROVAL` | `false` | Hold for human approval; use `approvalRequestId` / `getApprovalStatus` |
| `MONITOR` | `false` | Observability-only signal; do not treat as permission to execute |

Only `ALLOW` sets `decision.allowed` to `true`. Treat every other decision as non-executing unless your integration policy explicitly defines otherwise for `MONITOR`.

## Metering

```typescript
await session.recordModelCall({
  provider: "openai",
  model: "gpt-4o",
  inputTokens: 120,
  outputTokens: 40,
});
```

Use `completeMeteringSpan(spanId, …)` to PATCH an open span when usage completes asynchronously.

## Data access

```typescript
const result = await session.authorizeDataAccess({
  resource: "customer.profile",
  fields: ["email", "ssn"],
  purpose: "support_summary",
  accessMode: "READ",
});
```

## Behavior

- **Fail-closed by default** — network and timeout failures surface as `RAIError` with code `RAI_UNAVAILABLE` unless `failClosed: false`. When RAI is unavailable, do not execute consequential side effects.
- **Timeouts** — `timeoutMs` defaults to 30 seconds and uses `AbortController`.
- **Idempotency** — pass `idempotencyKey` to `authorizeAction` to send `Idempotency-Key`.
- **Runtime credentials** — pass `apiKey` from server-side environment or secrets management. Never embed agent keys in browser-side JavaScript.
- **Version headers** — requests include `User-Agent: rai-sdk-ts/<version>` and `X-RAI-SDK-Version`.
- **API compatibility** — `API_RANGE` is `>=1.0.0,<2.0.0` for the `/sdk/v1` contract.
- **Delegation** — pass `delegationId` on `startSession` to bind a grant for this instance; ended sessions are not reused unless `allowEndedSessionReuse: true`.

## Error handling

Failed API responses and fail-closed transport errors throw `RAIError` with:

- `code` — machine-readable error code
- `retryable` — whether a retry may succeed
- `statusCode` — HTTP status when available
- `details` — structured error details

## Public API

| Export | Description |
| --- | --- |
| `RAIClient` | HTTP client for `/sdk/v1` (`health`, `heartbeat`, `startSession`, `reportExecution`, `getDecision`, `getApprovalStatus`) |
| `Session` | Governed session handle (`observeInput`, `authorizeAction`, `authorizeDataAccess`, `recordUsage`, `observeOutput`, `end`, …) |
| `Decision` | Authorization decision wrapper |
| `RAIError` | Structured SDK/API error |
| `ConfigurationProvenanceMetadata` | Optional config provenance keys for metadata |
| `SDK_VERSION` | Package version string (`0.2.0`) |
| `API_RANGE` | Supported server API semver range |

## Module Format

This release ships **CommonJS** (`require`) with TypeScript declarations.

The `exports` map exposes:

```json
{
  ".": {
    "require": "./dist/index.js",
    "types": "./dist/index.d.ts"
  }
}
```

Native ESM (`import`) support is planned as a follow-up dual-build (`"import"` condition). For ESM projects today, use dynamic `import()` of the CJS build or a bundler that resolves CJS interop.

## Development

```bash
npm install
npm test
npm pack --dry-run
```

## License

Apache-2.0 — see [LICENSE](./LICENSE).
