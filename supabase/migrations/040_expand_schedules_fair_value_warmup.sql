-- Expand schedules.kind allowed values to include fair_value_warmup

DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'schedules_kind_check'
    ) THEN
        ALTER TABLE schedules DROP CONSTRAINT schedules_kind_check;
    END IF;

    ALTER TABLE schedules
        ADD CONSTRAINT schedules_kind_check
        CHECK (kind IN ('data_load', 'analysis_run', 'rebalance_run', 'trading_decision_v3', 'fair_value_warmup'));
END $$;
