-- Expand schedules.kind allowed values to include trading_decision_v3

DO $$
BEGIN
    -- Drop existing check constraint if present
    IF EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'schedules_kind_check'
    ) THEN
        ALTER TABLE schedules DROP CONSTRAINT schedules_kind_check;
    END IF;

    -- Recreate check constraint with the expanded allowed set
    ALTER TABLE schedules
        ADD CONSTRAINT schedules_kind_check
        CHECK (kind IN ('data_load', 'analysis_run', 'rebalance_run', 'trading_decision_v3'));
END $$;
