-- 052_job_schedules_research.sql — schedule seeds missing from the
-- applied migration set. The worker prefers supabase/migrations over
-- db/migrations_postgres, so the earnings-watch/read-through seeds in
-- db/migrations_postgres/029 never landed in environments using this
-- set — a silently unscheduled job looks like a job that "didn't run".
-- research: weekly routine pass (spec: routine deterministic updates +
-- event triggers, not every tick). Post-earnings refreshes come from
-- manual POST /admin/research/{sym} or the next weekly pass —
-- same-day rows are skipped by the job itself.
SELECT pg_advisory_xact_lock(715052);

INSERT INTO job_definitions (name, label, cron, enabled, cooldown_min)
VALUES ('earnings-watch', 'Earnings-day watcher',
        '*/30 12-13,20-23 * * 1-5', true, 25),
       ('read-through', 'Extended-hours repricing',
        '15,45 13,20-21 * * 1-5', true, 25),
       ('research', 'AI-tailwind research engine',
        '30 14 * * 0', true, 60)
ON CONFLICT (name) DO UPDATE SET
    -- seed ONLY a never-scheduled row (cron IS NULL); a hand-set
    -- schedule — including a deliberate disable — is authoritative
    cron         = COALESCE(job_definitions.cron, EXCLUDED.cron),
    enabled      = CASE WHEN job_definitions.cron IS NULL
                        THEN EXCLUDED.enabled
                        ELSE job_definitions.enabled END,
    cooldown_min = COALESCE(job_definitions.cooldown_min,
                            EXCLUDED.cooldown_min);
