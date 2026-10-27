# Backup, restore, and disaster recovery

VigilRAI Community Edition is powered by Ztechnium. This note covers one instance: its database, optional object storage, and secrets.

## Scope

Protect:

- PostgreSQL (registry, identity, approvals, enforcement receipts, evidence metadata, risk, assurance, governance, portfolio, SDK sessions)
- Object storage (when `OBJECT_STORAGE_BACKEND` is `s3`/`minio`)
- Secrets (API keys are hashed; webhook secrets hashed; provider keys in secret manager)

## RPO / RTO concepts

| Tier | RPO | RTO | Notes |
|------|-----|-----|-------|
| Pilot | ≤ 24h | ≤ 4h | Nightly logical dump |
| Production | ≤ 1h | ≤ 1h | Continuous WAL + hourly base |
| Regulated | ≤ 15m | ≤ 30m | Cross-region replica + tested restore |

## Backup procedure (PostgreSQL)

```bash
# Logical dump (pilot)
pg_dump "$DATABASE_URL" --format=custom --file="rai-$(date -u +%Y%m%dT%H%M%SZ).dump"

# Or continuous: configure managed Postgres PITR / WAL archiving
```

Store dumps in a separate account/region. Encrypt at rest.

## Restore procedure

```bash
# 1. Provision empty Postgres
# 2. Restore dump
pg_restore --clean --if-exists --dbname="$DATABASE_URL" rai-YYYYMMDD.dump

# 3. Run migrations to head (no-op if dump is current)
alembic upgrade head

# 4. Verify
curl -sf "$RAI_BASE_URL/ready"
curl -sf "$RAI_BASE_URL/version"
curl -sf "$RAI_BASE_URL/sdk/v1/health"
```

## Post-restore checks

1. Invited members can call the product APIs their roles allow. A user with no membership cannot.
2. A runtime credential still authenticates.
3. Historical portfolio reports and enforcement receipts intact
4. SDK session trajectory IDs resolve under WP5

## Fail-closed outage behavior

When RAI is unavailable and integration `fail_closed=true`:

- `authorize_action()` returns `DENY` / `RAI_UNAVAILABLE`
- Customer SDKs raise `RAIError` and **must not** execute consequential side effects

## DR drill

Quarterly: restore into isolated environment, run `pytest tests/sdk/`, exercise one SDK authorize cycle, capture evidence for compliance.
