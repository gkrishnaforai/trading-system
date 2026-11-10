-- live-price overlay: one batched fetch → one table → all readers
-- stitch onto daily_bars. 15-min cadence covers premarket → close.
SELECT pg_advisory_xact_lock(715194);

CREATE TABLE IF NOT EXISTS symbol_live_ticks (
  symbol TEXT NOT NULL, as_of DATE NOT NULL,
  last_px NUMERIC, volume NUMERIC,
  ts TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (symbol, as_of));

INSERT INTO job_definitions (name, label, cron, enabled, cooldown_min,
                             priority)
VALUES ('live-bars', 'Live price overlay (15-min)',
        '*/15 13-21 * * 1-5', true, 12, 15)
ON CONFLICT (name) DO UPDATE SET
    cron         = COALESCE(job_definitions.cron, EXCLUDED.cron),
    enabled      = CASE WHEN job_definitions.cron IS NULL
                        THEN EXCLUDED.enabled
                        ELSE job_definitions.enabled END,
    priority     = EXCLUDED.priority;
