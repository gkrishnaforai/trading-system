-- Catalyst-alerts slim-down — the hourly `alerts` scan piggybacked
-- nine other jobs (alert/mover/pick outcome grading, a full
-- rule-breakers engine pass, after-hours boards, pt-watch) and kept
-- timing out at 15m. The scan now only collects + auto-reviews; the
-- tails either already have jobs or get their own here:
--
--   after-hours   extended-hours movers — was opportunistic inside
--                 the scan; now windowed on its own cron
--   pt-watch      analyst-PT snapshot — was once/day inside the scan
--
-- alert outcomes were already covered by `outcomes`; mover grading by
-- `mover-quality`; rule-breakers by `rule-breakers`; pick outcomes
-- were folded into `outcomes` (they had no scheduled home).

INSERT INTO job_definitions (name, label, purpose, cron, enabled,
                             depends_on, dep_max_age_h, cooldown_min,
                             priority)
VALUES
 ('after-hours', 'Extended-hours movers',
  'Post/pre-market movers board — windowed; no-ops outside the session',
  '*/20 11-13,20-23 * * 1-5', true, NULL, 24, 10, 16),
 ('pt-watch', 'Analyst PT watch',
  'Daily PT/drift snapshot per tracked name — idempotent per as_of',
  '45 21 * * 1-5', true, NULL, 24, 60, 17)
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

UPDATE job_definitions
SET purpose = 'Alert collectors + bounded auto-review — grading and '
              'engine tails moved to their own jobs',
    updated_at = now()
WHERE name = 'alerts';
