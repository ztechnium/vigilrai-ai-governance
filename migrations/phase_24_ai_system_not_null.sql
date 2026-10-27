-- Phase 24: AI System Orphan Cleanup
-- Add NOT NULL constraint to ai_systems.organization_id
--
-- PREREQUISITES:
--   1. All orphan AI systems must be assigned to organizations
--   2. Run verification: python -m rai_gateway.cli orphan-cleanup verify
--   3. Verify output: "All AI systems have organization assignments!"
--
-- IMPORTANT:
--   This migration will FAIL if any AI systems still have NULL organization_id.
--   This is intentional - it ensures all data is cleaned up first.

BEGIN;

-- Step 1: Verify no orphans exist (safety check)
DO $$
DECLARE
    orphan_count INTEGER;
BEGIN
    SELECT COUNT(*) INTO orphan_count
    FROM ai_systems
    WHERE organization_id IS NULL;
    
    IF orphan_count > 0 THEN
        RAISE EXCEPTION 'Cannot add NOT NULL constraint: % AI system(s) still have NULL organization_id. Run orphan cleanup first.', orphan_count;
    END IF;
    
    RAISE NOTICE 'Verification passed: All AI systems have organization assignments';
END $$;

-- Step 2: Add NOT NULL constraint
-- Note: The constraint is already defined in the SQLAlchemy model as nullable=False,
-- but this was not enforced at the database level for historical data.
-- This migration adds the database-level constraint.

-- First, check if the constraint already exists (idempotent migration)
DO $$
BEGIN
    -- Try to add the constraint
    -- PostgreSQL will raise an error if it already exists or if data violates it
    BEGIN
        ALTER TABLE ai_systems
        ALTER COLUMN organization_id SET NOT NULL;
        
        RAISE NOTICE 'Successfully added NOT NULL constraint to ai_systems.organization_id';
    EXCEPTION
        WHEN others THEN
            -- Check if the column is already NOT NULL
            IF EXISTS (
                SELECT 1
                FROM information_schema.columns
                WHERE table_name = 'ai_systems'
                  AND column_name = 'organization_id'
                  AND is_nullable = 'NO'
            ) THEN
                RAISE NOTICE 'NOT NULL constraint already exists on ai_systems.organization_id (no action needed)';
            ELSE
                -- Re-raise the error if it's something else
                RAISE;
            END IF;
    END;
END $$;

-- Step 3: Verify constraint is in place
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_name = 'ai_systems'
          AND column_name = 'organization_id'
          AND is_nullable = 'NO'
    ) THEN
        RAISE EXCEPTION 'Verification failed: NOT NULL constraint was not applied correctly';
    END IF;
    
    RAISE NOTICE 'Verification passed: NOT NULL constraint is in place';
END $$;

-- Step 4: Final report
DO $$
DECLARE
    total_systems INTEGER;
    systems_per_org RECORD;
BEGIN
    SELECT COUNT(*) INTO total_systems FROM ai_systems;
    
    RAISE NOTICE '====================================';
    RAISE NOTICE 'Phase 24 Migration Complete';
    RAISE NOTICE '====================================';
    RAISE NOTICE 'Total AI Systems: %', total_systems;
    RAISE NOTICE 'All AI systems have organization assignments';
    RAISE NOTICE 'NOT NULL constraint enforced at database level';
    RAISE NOTICE '====================================';
    
    -- Show distribution per organization
    RAISE NOTICE 'AI Systems per Organization:';
    FOR systems_per_org IN
        SELECT o.name, COUNT(a.id) as system_count
        FROM organizations o
        LEFT JOIN ai_systems a ON a.organization_id = o.id
        GROUP BY o.id, o.name
        ORDER BY system_count DESC, o.name
    LOOP
        RAISE NOTICE '  %: % system(s)', systems_per_org.name, systems_per_org.system_count;
    END LOOP;
END $$;

COMMIT;

-- Rollback script (save separately if needed):
-- ALTER TABLE ai_systems ALTER COLUMN organization_id DROP NOT NULL;
