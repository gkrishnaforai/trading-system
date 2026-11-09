-- session-tape windows were wrong-TZ: both ended before close.
-- RTH is 14:30-21:00 UTC year-round (9:30-16:00 ET).
-- intraday-tape  */15 13-20  -> */15 14-21 (was missing 3-4pm close)
-- intraday-regime 0 8-17     -> 0,30 14-21 (was 3am-noon ET only)
SELECT pg_advisory_xact_lock(715191);

UPDATE job_definitions SET cron = '*/15 14-21 * * 1-5'
 WHERE name = 'intraday-tape';
UPDATE job_definitions SET cron = '10,40 14-21 * * 1-5'
 WHERE name = 'intraday-regime';
