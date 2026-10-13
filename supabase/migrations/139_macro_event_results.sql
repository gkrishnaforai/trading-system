-- Capture release outcomes on macro_event_overrides and re-run the
-- verifier at post-release times so same-day actuals land on the boards
-- 12:05 UTC = 8:05 ET pre-check, 14:05 UTC = post 8:30 ET prints,
-- 19:05 UTC = post 14:00 ET FOMC

ALTER TABLE macro_event_overrides
    ADD COLUMN IF NOT EXISTS actual   numeric,
    ADD COLUMN IF NOT EXISTS estimate numeric,
    ADD COLUMN IF NOT EXISTS prev     numeric;

UPDATE job_definitions
SET cron = '5 12,14,19 * * *', updated_at = NOW()
WHERE name = 'econ-cal-verify';
