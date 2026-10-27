# API Compatibility & Upgrade Strategy

## Public contract

- Namespace: `/sdk/v1`
- Compatibility range advertised by SDKs and `/sdk/v1/health`: `>=1.0.0,<2.0.0`
- Protocol version: integer `1` on integrations / heartbeat

## Rules

1. Additive response fields are allowed within `/sdk/v1`.
2. Existing field meanings must not silently change.
3. Breaking changes require `/sdk/v2` (or new major SDK).
4. Deprecated fields receive a documented sunset (≥ 90 days for GA).
5. Internal `/v1/*` admin/domain APIs may evolve faster; customers should prefer `/sdk/v1`.

## SDK ↔ server

| SDK major | Supported server |
|-----------|------------------|
| 1.x | `/sdk/v1` |

Heartbeat returns `server_api_version` and `compatibility_range`. Clients should warn (not hard-fail) on unknown additive fields.

## Rollback

1. Deploy previous gateway image.
2. Do **not** downgrade Alembic past WP10 if new tables are populated — forward-fix instead.
3. SDKs remain compatible as long as `/sdk/v1` paths exist.

Evidence exports stay on this instance. There is no organization offboarding lifecycle.
