-- 056_job_schedule_stagger.sql — de-collide job crons.
--
-- The dispatcher fires every due job at once; seeds had several
-- same-minute collisions:
--   hourly :00  — alerts + regime (*/30) + leaps-mark (*/30) + flywheel
--   22:40       — theme-rotation + best-picks (weekdays)
--   Sat 09:00   — smallcap-eval + smallcap-discovery
--   Sat 14:00   — liquidity, then fund-snapshots 20min later
--
-- WHERE cron=<old> guards: only the seeded value is rewritten — a
-- hand-set schedule stays authoritative.

UPDATE job_definitions SET cron = '10 12-22 * * 1-5', updated_at = NOW()
 WHERE name = 'alerts' AND cron = '0 12-22 * * 1-5';

UPDATE job_definitions SET cron = '20 14,22 * * 1-5', updated_at = NOW()
 WHERE name = 'flywheel' AND cron = '0 14,22 * * 1-5';

UPDATE job_definitions SET cron = '50 22 * * *', updated_at = NOW()
 WHERE name = 'best-picks' AND cron = '40 22 * * *';

UPDATE job_definitions SET cron = '30 9 * * 6', updated_at = NOW()
 WHERE name = 'smallcap-discovery' AND cron = '0 9 * * 6';

UPDATE job_definitions SET cron = '20 12 * * 6', updated_at = NOW()
 WHERE name = 'fund-snapshots' AND cron = '20 14 * * 6';
