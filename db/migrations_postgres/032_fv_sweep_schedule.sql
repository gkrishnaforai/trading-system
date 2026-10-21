-- Weekly fair-value sweep. FV runs are otherwise event-driven — a
-- fundamentals fetch that lands outside the refresh-worker path (the
-- stock_insights snapshot writer) never triggers a recompute, so a
-- symbol can price on stale eps_forward for weeks. The sweep is the
-- floor: every Monday 08:00 ET (post-weekend estimate revisions,
-- pre-open) it refetches fundamentals for any symbol whose last
-- quarterly print postdates its snapshot, then re-resolves FV over
-- the tracked universe.

INSERT INTO job_definitions (name, label, cron, enabled, cooldown_min)
VALUES ('fv-sweep', 'Weekly fair-value sweep',
        '0 12 * * 1', true, 720)
ON CONFLICT (name) DO UPDATE SET
    cron = EXCLUDED.cron, enabled = EXCLUDED.enabled,
    cooldown_min = EXCLUDED.cooldown_min;
