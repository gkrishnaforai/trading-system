-- Hands-off schedules for the after-hours engines. Cron is 5-field
-- UTC (EDT windows shift an hour earlier in EST — the watcher
-- returns 'awaiting_print' harmlessly in dead slots).
--
-- earnings-watch: every 30 min across 20-23 + 12-13 UTC =
--   ~16:00-19:30 ET post-close and ~08:00-09:30 ET pre-open —
--   catches both AMC and BMO reporters.
-- read-through:   16:15/16:45 ET post-close and 09:15/09:45 ET
--   pre-open — repricing settles ~15min after the catalyst.

INSERT INTO job_definitions (name, label, cron, enabled, cooldown_min)
VALUES ('earnings-watch', 'Earnings-day watcher',
        '*/30 12-13,20-23 * * 1-5', true, 25),
       ('read-through', 'Extended-hours repricing',
        '15,45 13,20-21 * * 1-5', true, 25)
ON CONFLICT (name) DO UPDATE SET
    cron = EXCLUDED.cron, enabled = EXCLUDED.enabled,
    cooldown_min = EXCLUDED.cooldown_min;
