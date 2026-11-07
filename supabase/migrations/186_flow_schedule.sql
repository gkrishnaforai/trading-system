-- flow footprint nightly — post-close EOD data only, weekdays.
-- 21:30 UTC sits after the US close year-round (16:00 ET).
-- Seeds only if unset; a hand-set cron stays authoritative.
SELECT pg_advisory_xact_lock(715186);

INSERT INTO job_definitions (name, label, cron, enabled, cooldown_min)
VALUES ('flow', 'Institutional flow footprint',
        '30 21 * * 1-5', true, 60)
ON CONFLICT (name) DO UPDATE SET
    cron         = COALESCE(job_definitions.cron, EXCLUDED.cron),
    enabled      = CASE WHEN job_definitions.cron IS NULL
                        THEN EXCLUDED.enabled
                        ELSE job_definitions.enabled END,
    cooldown_min = COALESCE(job_definitions.cooldown_min,
                            EXCLUDED.cooldown_min);
