-- resolution block on fragility_daily — the deleveraging-cycle
-- phase (building → discharging → stabilizing → recovering) with
-- discharge/bottom evidence, answering 'more selloff or recovering'
-- from the same journal.
ALTER TABLE fragility_daily
    ADD COLUMN IF NOT EXISTS resolution JSONB NOT NULL DEFAULT '{}';
