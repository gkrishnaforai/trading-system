-- same-day earnings extraction — every 45 min during the US day,
-- only on book symbols reporting today/yesterday. Guidance badge
-- lands within the hour of a filing, not overnight.
SELECT pg_advisory_xact_lock(715193);

INSERT INTO job_definitions (name, label, cron, enabled, cooldown_min,
                             priority)
VALUES ('earnings-today', 'Same-day earnings extraction',
        '*/45 13-22 * * 1-5', true, 40, 18)
ON CONFLICT (name) DO UPDATE SET
    cron         = COALESCE(job_definitions.cron, EXCLUDED.cron),
    enabled      = CASE WHEN job_definitions.cron IS NULL
                        THEN EXCLUDED.enabled
                        ELSE job_definitions.enabled END,
    priority     = EXCLUDED.priority,
    cooldown_min = COALESCE(job_definitions.cooldown_min,
                            EXCLUDED.cooldown_min);
