-- Scheduler tuning — job timing fixes and supervisor enablement.
-- job_definitions crons are UTC; schedules rows carry their own timezone.

-- Enable the custodian supervisor: retries silently-failed jobs and
-- escalates to the board after repeated failures. Without it, a broken
-- job errors invisibly.
UPDATE job_definitions
SET enabled = true, updated_at = NOW()
WHERE name = 'custodian';

-- eod_fair_value fired 19:30 UTC = 15:30 ET, i.e. on pre-close prices.
-- Move to 21:30 UTC = 17:30 EDT / 16:30 EST — post-close year-round.
-- (next_run_at is recomputed from cron by the tick after its next run.)
UPDATE schedules
SET cron_expression = '30 21 * * 1-5', updated_at = NOW()
WHERE profile = 'eod_fair_value';

-- intraday_prices_only stopped at 15:45 ET and missed the 16:00 close
-- bar. Extend the hour window so the close print lands.
UPDATE schedules
SET cron_expression = '0,15,30,45 9-16 * * 1-5', updated_at = NOW()
WHERE profile = 'intraday_prices_only';
