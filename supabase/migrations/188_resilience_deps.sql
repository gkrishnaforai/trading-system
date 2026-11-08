-- resilience chain ordering: resilience consumes fact-checks,
-- earnings-quality and flow — it must not fire before they land.
-- depends_on requires a clean job_runs row within dep_max_age_h;
-- 60h lets Friday's nightly runs feed Sunday's score.
-- priority ties: producers first, consumer last.
SELECT pg_advisory_xact_lock(715188);

INSERT INTO job_definitions (name, label, cron, enabled, cooldown_min)
VALUES ('earnings-quality', 'Forensic earnings-quality screen',
        '0 22 * * 1-5', true, 60)
ON CONFLICT (name) DO UPDATE SET
    cron         = COALESCE(job_definitions.cron, EXCLUDED.cron),
    enabled      = CASE WHEN job_definitions.cron IS NULL
                        THEN EXCLUDED.enabled
                        ELSE job_definitions.enabled END,
    cooldown_min = COALESCE(job_definitions.cooldown_min,
                            EXCLUDED.cooldown_min);

-- producers run earlier in the nightly window; consumer waits
UPDATE job_definitions SET priority = 20 WHERE name = 'flow';
UPDATE job_definitions SET priority = 20 WHERE name = 'earnings-quality';
UPDATE job_definitions SET priority = 40 WHERE name = 'resilience-validate';
UPDATE job_definitions SET priority = 50 WHERE name = 'resilience';

UPDATE job_definitions
   SET depends_on = ARRAY['resilience-validate','earnings-quality','flow'],
       dep_max_age_h = 60
 WHERE name = 'resilience';
