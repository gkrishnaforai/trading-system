-- 235_session_tape_arc.sql — full-day session tape coverage.
--
-- Gathering used to start mid-morning: market-stability ran UTC
-- 13-20 (8/9am-4/5pm ET — drifting marks across DST) and
-- premarket-tape was never enabled. Now the arc starts at
-- pre-market open and runs through after-hours, all in ET so DST
-- can't move the windows (the migration-196 convention).
SELECT pg_advisory_xact_lock(715235);

-- pre-market gathering from 4:00 ET — every 30 min, hourly slots
-- (h04..h08 + final) journal the gap's firm/fade drift per hour.
UPDATE job_definitions
   SET cron = '*/30 4-9 * * 1-5', enabled = true,
       timezone = 'America/New_York', updated_at = NOW()
 WHERE name = 'premarket-tape';

-- stability: RTH + extended arc in ET — premarket mark if bars flow
-- at 9:00-9:29, open→close hourly marks, afterhours 16:00-20:00.
UPDATE job_definitions
   SET cron = '*/15 9-20 * * 1-5', timezone = 'America/New_York',
       enabled = true, updated_at = NOW()
 WHERE name = 'market-stability';

-- weekly retention — spine marks persist, intermediates expire >7d.
INSERT INTO job_definitions (name, label, purpose, cron, enabled,
                             priority)
VALUES ('tape-purge', 'Session tape retention (weekly)',
        'market_stability_snapshots older than 7d drop intermediate'
        ' marks — day-spine (premarket/open/close/afterhours)'
        ' persists as the graded-prediction record',
        '0 0 * * 0', true, 80)
ON CONFLICT (name) DO UPDATE SET cron = EXCLUDED.cron,
    enabled = true, updated_at = NOW();
