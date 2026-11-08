-- schedule gaps: guidance + sector-timing had no cron; spread
-- the 22:00 collision (earnings-quality vs flywheel same-minute).
-- Seeds only unset crons; hand-set schedules stay authoritative.
SELECT pg_advisory_xact_lock(715190);

INSERT INTO job_definitions (name, label, cron, enabled, cooldown_min)
VALUES ('guidance', 'Guidance intelligence', '30 22 * * 1-5', true, 60),
       ('sector-timing', 'Sector timing cycles', '0 4 * * 6', true, 60)
ON CONFLICT (name) DO UPDATE SET
    cron    = COALESCE(job_definitions.cron, EXCLUDED.cron),
    enabled = CASE WHEN job_definitions.cron IS NULL
                   THEN EXCLUDED.enabled ELSE job_definitions.enabled END;

-- stagger same-minute pairs so producers don't stampede
UPDATE job_definitions SET cron = '15 22 * * 1-5'
 WHERE name = 'earnings-quality' AND cron = '0 22 * * 1-5';
UPDATE job_definitions SET priority = 25 WHERE name = 'flywheel';
