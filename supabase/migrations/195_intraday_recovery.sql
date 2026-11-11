-- 195_intraday_recovery.sql — 5-minute session bars + the recovery-
-- confirmation eval journal. intraday_bars is the ONE producer every
-- intraday consumer reads (same contract as symbol_live_ticks but
-- real OHLCV); intraday_recovery_evals journals one eval per
-- completed bar per symbol — the persistence substrate for the
-- 'does the signal survive 30/60/90m' metric.

SELECT pg_advisory_xact_lock(715195);

CREATE TABLE IF NOT EXISTS intraday_bars (
  symbol    TEXT NOT NULL,
  bar_ts    TIMESTAMPTZ NOT NULL,
  open      NUMERIC, high NUMERIC, low NUMERIC, close NUMERIC,
  volume    NUMERIC,
  PRIMARY KEY (symbol, bar_ts));
CREATE INDEX IF NOT EXISTS idx_ibars_sym_ts
    ON intraday_bars (symbol, bar_ts DESC);

CREATE TABLE IF NOT EXISTS intraday_recovery_evals (
  id              bigserial PRIMARY KEY,
  symbol          TEXT NOT NULL,
  as_of           DATE NOT NULL,
  bar_ts          TIMESTAMPTZ NOT NULL,   -- the bar evaluated (final)
  signal          TEXT NOT NULL,          -- STRONG/CONFIRMED/IMPROVING/
                                          -- WATCH/FAILED_REBOUND/DATA_BLOCKED
  score           NUMERIC,
  legs            JSONB,                  -- score legs + ctx snapshot
  rules_version   TEXT NOT NULL,
  engine_version  TEXT NOT NULL,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (symbol, bar_ts));
CREATE INDEX IF NOT EXISTS idx_ire_sym_asof
    ON intraday_recovery_evals (symbol, as_of DESC);
CREATE INDEX IF NOT EXISTS idx_ire_signal
    ON intraday_recovery_evals (signal, as_of);

INSERT INTO job_definitions (name, label, cron, enabled, cooldown_min,
                             priority)
VALUES ('intraday-recovery', 'Intraday recovery confirm (5-min)',
        '*/5 14-21 * * 1-5', true, 4, 20)
ON CONFLICT (name) DO UPDATE SET
    cron         = COALESCE(job_definitions.cron, EXCLUDED.cron),
    enabled      = CASE WHEN job_definitions.cron IS NULL
                        THEN EXCLUDED.enabled
                        ELSE job_definitions.enabled END,
    priority     = EXCLUDED.priority;
