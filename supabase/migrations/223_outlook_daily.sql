-- Horizon-ladder journal — the outlook block (next_day / weeks /
-- months verdicts + evidence) journaled once daily so each horizon
-- can be graded on its own clock: next-day calls verify against
-- daily_bars fast, months accrue the slow track record.

CREATE TABLE IF NOT EXISTS outlook_daily (
  date        date        PRIMARY KEY,
  horizons    jsonb       NOT NULL,
  created_at  timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS outlook_daily_date_idx
  ON outlook_daily (date DESC);
