-- 5x Scout split — the monolithic `smallcap` job (members eval +
-- discovery + tail refreshes in one run) kept timing out at 15m
-- because member evals were sequential. Now three schedulable stage
-- jobs that can fire the same minute and run in parallel:
--
--   smallcap-eval       members deep-eval (parallel inside, sem=6)
--   smallcap-discovery  pool cursor sweep → auto-add qualifiers
--   smallcap-tail       research_missing + flywheel + momentum
--
-- All on weekend idle hours (Sat/Sun morning UTC). `smallcap` stays
-- registered but unscheduled — the manual button still runs the full
-- pass, and 'all' composes the stages in order.
--
-- dep_max_age_h=48: flywheel's last weekday run (Fri 22:00 UTC) is
-- ~35h stale by Sunday — the 24h default would gate the Sunday run.

INSERT INTO job_definitions (name, label, purpose, cron, enabled,
                             depends_on, dep_max_age_h, cooldown_min,
                             priority)
VALUES
 ('smallcap-eval', '5x Scout — member eval',
  'Parallel deep eval of all members — gates, tiers, snapshots',
  '0 9 * * 6,0', true, '{flywheel}', 48, 60, 41),
 ('smallcap-discovery', '5x Scout — discovery sweep',
  '$1-30B pool cursor sweep — light gates → deep eval → auto-add',
  '0 9 * * 6', true, '{flywheel}', 48, 60, 42),
 ('smallcap-tail', '5x Scout — tail refresh',
  'Research missing checklists, flywheel refresh, momentum flags',
  '0 11 * * 6,0', true, '{smallcap-eval}', 48, 60, 43)
ON CONFLICT (name) DO UPDATE SET
    label = EXCLUDED.label,
    purpose = EXCLUDED.purpose,
    cron = EXCLUDED.cron,
    enabled = EXCLUDED.enabled,
    depends_on = EXCLUDED.depends_on,
    dep_max_age_h = EXCLUDED.dep_max_age_h,
    cooldown_min = EXCLUDED.cooldown_min,
    priority = EXCLUDED.priority,
    updated_at = now();

-- the monolith goes manual-only — scheduled work moves to the stages
UPDATE job_definitions
SET enabled = false, cron = NULL,
    purpose = 'Full 5x Scout pass (manual) — stages run on weekends',
    updated_at = now()
WHERE name = 'smallcap';
