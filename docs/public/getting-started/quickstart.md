# Quickstart

Govern one tool call on a local community-edition instance.

## Prerequisites

Start the stack with the [README](../../../README.md) or [Deploy with Docker](../../deployment/docker.md).

- API at `http://localhost:8001`
- Sign-in page at `http://localhost:3000`
- Bootstrap admin `admin@raigateway.local` / `ChangeMe123!`

There is no public signup. Sign in, then invite teammates from Team & roles.

## Step 1: Sign in and copy a token

```bash
curl -s -X POST http://localhost:8001/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@raigateway.local","password":"ChangeMe123!"}'
```

Use the `access_token` value as `$TOKEN`. Do not send `X-Organization-ID`. Membership on this instance is enough.

## Step 2: Register an AI system

```bash
curl -X POST http://localhost:8001/v1/ai-systems \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "system_key": "my-agent",
    "name": "My First Agent",
    "risk_tier": "MEDIUM"
  }'
```

## Step 3: Create an agent and a version

Use **AI Systems** in the console, or the REST API, to create an agent and a version under that system.

## Step 4: Create a runtime identity

```bash
curl -X POST http://localhost:8001/v1/runtime-identities \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "agent_id": "<agent-id>",
    "agent_version_id": "<version-id>",
    "name": "dev-identity",
    "environment": "DEVELOPMENT"
  }'
```

## Step 5: Issue credentials

```bash
curl -X POST http://localhost:8001/v1/runtime-identities/{identity_id}/credentials \
  -H "Authorization: Bearer $TOKEN"
```

Save the returned credential secret. It is shown only once.

## Step 6: Authorize an action

```bash
curl -X POST http://localhost:8001/v1/runtime/actions/authorize \
  -H "X-RAI-Agent-Key: rai_live_..." \
  -H "Content-Type: application/json" \
  -d '{
    "tool_name": "send_email",
    "parameters": {"to": "test@example.com", "subject": "Hello"}
  }'
```

## Step 7: Execute when the decision allows it

```bash
curl -X POST http://localhost:8001/v1/runtime/actions/execute \
  -H "X-RAI-Agent-Key: rai_live_..." \
  -H "Content-Type: application/json" \
  -d '{
    "tool_name": "send_email",
    "parameters": {"to": "test@example.com", "subject": "Hello", "body": "Test"}
  }'
```

## Or run the bundled examples

The developer lab does these steps for Support AI, Sales AI, and the other reference agents. Follow [examples/developer_lab/README.md](../../../examples/developer_lab/README.md).

## Next steps

- Add [content and tool policy rules](../integration/rest-api.md)
- Integrate via [Python SDK](../integration/python-sdk.md) or [TypeScript SDK](../integration/typescript-sdk.md)
- Review [fail-closed behavior](../operations/fail-closed.md)
