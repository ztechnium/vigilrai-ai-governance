# Database Migrations

This directory contains database migration scripts for the RAI Gateway.

## Migration Workflow

Migrations are run manually by operators after data cleanup is complete.

### Phase 24: AI System Orphan Cleanup

Before running the NOT NULL migration:

1. **Report Orphans:**
   ```bash
   python -m rai_gateway.cli orphan-cleanup report
   ```

2. **Assign Organizations (Interactive):**
   ```bash
   python -m rai_gateway.cli orphan-cleanup interactive
   ```

3. **Verify No Orphans:**
   ```bash
   python -m rai_gateway.cli orphan-cleanup verify
   ```

4. **Run Migration:**
   ```bash
   psql $DATABASE_URL < migrations/phase_24_ai_system_not_null.sql
   ```

## Migration Files

- `phase_24_ai_system_not_null.sql` - Add NOT NULL constraint to ai_systems.organization_id (Phase 24)

## Running Migrations

### PostgreSQL

```bash
psql -h <host> -U <user> -d <database> -f migrations/<migration_file>.sql
```

### With Environment Variable

```bash
psql $DATABASE_URL -f migrations/<migration_file>.sql
```

## Rollback

Each migration should have a corresponding rollback script when possible.

## Testing Migrations

Always test migrations on a copy of production data before running in production:

```bash
# 1. Take a backup
pg_dump $DATABASE_URL > backup.sql

# 2. Test migration on staging
psql $STAGING_DATABASE_URL < migrations/<migration_file>.sql

# 3. Verify no issues
# 4. Run on production
psql $DATABASE_URL < migrations/<migration_file>.sql
```
