-- 196_intraday_cron_et.sql — session jobs on exchange timezone
-- (the migration-178 convention: market-hours crons in ET so they
-- don't drift across DST).
--
-- 191 rewrote intraday-regime's hours to 14-21 but left timezone
-- 'America/New_York' — it fired 14:10-21:40 ET: the entire
-- 9:30am-2pm session had no regime overlay (the regime page's
-- intraday block sat stale at the 8am row all morning), then it ran
-- pointlessly until 9:40pm.
--
-- intraday-tape / intraday-recovery are UTC rows at 14-21 — covers
-- RTH in EST but loses the 9:30-10:00 opening bars when EDT makes
-- 14:00 UTC = 10:00 ET (the opening-range leg would go dark all
-- summer). Normalized to ET hours so the window is correct
-- year-round.
SELECT pg_advisory_xact_lock(715196);

UPDATE job_definitions
   SET cron = '10,40 9-16 * * 1-5', updated_at = NOW()
 WHERE name = 'intraday-regime';

UPDATE job_definitions
   SET cron = '*/15 9-16 * * 1-5',
       timezone = 'America/New_York', updated_at = NOW()
 WHERE name = 'intraday-tape';

UPDATE job_definitions
   SET cron = '*/5 9-16 * * 1-5',
       timezone = 'America/New_York', updated_at = NOW()
 WHERE name = 'intraday-recovery';
