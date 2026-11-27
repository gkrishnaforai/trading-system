-- 242_session_forecasts.sql — session-to-session forecast journal.
--
-- Ties the existing day arc (premarket_snapshots → intraday_evals →
-- daily_bars) into a cross-session prediction: after the close, the
-- day's tape becomes the baseline prior for the next session; before
-- the open, overnight futures/gaps update it; next day's close grades
-- the call. One row per (forecast_date, stage) — the baseline is
-- never overwritten, stages land as separate rows, outcomes journal
-- onto the row rather than replacing the forecast.
--
-- Restricted surface: admin-only (market_forecast flag) — this is a
-- Group-2 market-prediction read, not a buy signal.

CREATE TABLE IF NOT EXISTS session_forecasts (
  id                     bigserial PRIMARY KEY,
  forecast_date          date        NOT NULL,  -- session being predicted
  baseline_session       date        NOT NULL,  -- session whose tape seeded it
  baseline_session_type  text,                  -- 'full'|'early_close'|'unknown'
  stage                  text        NOT NULL,  -- 'baseline'|'premarket'
  tape                   jsonb,                 -- observed session-tape features
  overnight              jsonb,                 -- futures/gaps/yields before open
  forecast               jsonb,                 -- score + band + components + basis
  actual_ret             numeric,               -- graded: target-day QQQ close/prev-1
  hit                    boolean,               -- did the directional call land
  graded_at              timestamptz,
  created_at             timestamptz NOT NULL DEFAULT now(),
  UNIQUE (forecast_date, stage)
);

CREATE INDEX IF NOT EXISTS session_forecasts_date_idx
  ON session_forecasts (forecast_date DESC);

-- one job, stage follows the clock: 4:00-9:30 ET -> 'premarket' update;
-- 16:05+ ET -> 'baseline' for the next session; every pass sweeps the
-- ungraded backlog. Outside those windows run() no-ops cheaply.
INSERT INTO job_definitions (name, label, purpose, kind, cron,
                             enabled, priority)
VALUES ('session-forecast',
        'Session-to-session direction forecast',
        'Post-close tape baseline + pre-market update + outcome grading'
        ' for the next-session direction score',
        'job', '*/15 4-17 * * 1-5', true, 60)
ON CONFLICT (name) DO UPDATE SET cron = EXCLUDED.cron,
    enabled = true, updated_at = NOW();
