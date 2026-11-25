-- selloff cadence: market changes mean the list changes.
-- live-bars refreshes daily_bars every 15min 13-21 UTC weekdays
-- and regime snapshots every 30min, so run the scan at :05/:35 —
-- five minutes after each bars batch — through market hours plus
-- two post-close runs for the EOD journal. ~19 runs/weekday, each
-- well under its 5min timeout.
UPDATE job_definitions
   SET cron = '5,35 13-22 * * 1-5',
       timezone = 'UTC'
 WHERE name = 'selloff';

-- it reads live-bars output intraday and flywheel aggregates, so
-- depend on both; 24h max-age is satisfied by nightly flywheel.
UPDATE job_definitions
   SET depends_on = '{flywheel,live-bars}'
 WHERE name = 'selloff';
