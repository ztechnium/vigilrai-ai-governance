# REST API

The RAI Control Plane REST API provides runtime enforcement and registry management endpoints.

## Base URL

```
http://localhost:8001
```

Configure via `NEXT_PUBLIC_API_BASE_URL` in the UI or your SDK client.

## Authentication

### Runtime Operations

```
X-RAI-Agent-Key: rai_live_...
```

### Admin Operations

```
Authorization: Bearer eyJ...
```

Obtain a Bearer token from `POST /v1/auth/login` with the bootstrap admin or a teammate you invited. This edition does not have `POST /v1/public/register` and does not use `X-Organization-ID`.

## Key Endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | `/v1/runtime/actions/authorize` | Evaluate policy before action |
| POST | `/v1/runtime/actions/execute` | Execute authorized action |
| GET | `/v1/runtime/enforcement/receipts` | Query enforcement receipts |
| POST | `/v1/ai-systems` | Register AI system |
| POST | `/v1/runtime-identities` | Create runtime identity |
| POST | `/v1/approval-requests` | Request human approval |

## OpenAPI

Interactive documentation available at `/docs` on the running backend.

## Response Headers

All responses include `x-trace-id` for correlation and debugging.
