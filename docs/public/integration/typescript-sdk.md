# TypeScript SDK

Install and use the RAI Control Plane TypeScript SDK for Node.js and browser clients.

## Installation

```bash
npm install @ztechnium/rai-sdk
```

## Configuration

```typescript
import { RAIClient } from "@ztechnium/rai-sdk";

const client = new RAIClient({
  baseUrl: process.env.RAI_BASE_URL!,
  credential: process.env.RAI_CREDENTIAL!,
});
```

## Authorize and Execute

```typescript
const result = await client.authorize({
  toolName: "send_email",
  parameters: { to: "user@example.com", subject: "Hello" },
});

if (result.decision === "allow") {
  await client.execute({
    toolName: "send_email",
    parameters: { to: "user@example.com", subject: "Hello", body: "..." },
  });
}
```

## Error Handling

- HTTP failures throw `RAIError`
- Policy denials return decision objects (not exceptions)

## GitHub

Source and examples: [rai-control-plane-sdk-typescript](https://github.com/ztechnium/rai-control-plane-sdk-typescript)
