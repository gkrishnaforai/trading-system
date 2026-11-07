-- resilience weekend cadence — validate Saturdays (slow XBRL pass),
-- score Sundays so the diff sees fresh verdicts. Seeds only rows
-- with no schedule yet; a hand-set cron stays authoritative.
SELECT pg_advisory_xact_lock(715184);

INSERT INTO job_definitions (name, label, cron, enabled, cooldown_min)
VALUES ('resilience-validate', 'Resilience fact-check (XBRL)',
        '0 3 * * 6', true, 120),
       ('resilience', 'Company resilience scorecards',
        '0 6 * * 0', true, 60)
ON CONFLICT (name) DO UPDATE SET
    cron         = COALESCE(job_definitions.cron, EXCLUDED.cron),
    enabled      = CASE WHEN job_definitions.cron IS NULL
                        THEN EXCLUDED.enabled
                        ELSE job_definitions.enabled END,
    cooldown_min = COALESCE(job_definitions.cooldown_min,
                            EXCLUDED.cooldown_min);
