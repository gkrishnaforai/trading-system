/*
 * Enable the intraday tape job — the 15-min state classifier was
 * registered but disabled, so evals only journaled when someone hit
 * /intraday (lazy). The session-tape page section needs the tick.
 * RTH 9:30-15:45 ET = 13:30-19:45 UTC; market_open_now() in
 * intraday_pulse guards the off-window ticks anyway.
 * No line comments or semicolons outside statements (splitter-safe).
 */

UPDATE job_definitions
SET cron = '*/15 13-20 * * 1-5',
    enabled = true,
    purpose = 'Journaled 15-min tape state during RTH (VWAP/VIX/leadership/breadth) — the session story on the regime page'
WHERE name = 'intraday-tape';
