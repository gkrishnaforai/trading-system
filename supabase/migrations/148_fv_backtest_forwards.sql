-- P6: materialized forward outcomes for FV backtesting.
-- The backtest previously ran O(runs × horizons) per-run SQL queries
-- against daily_bars — 1.5k runs timed out interactively. This table
-- materializes each (run, horizon) outcome in a single windowed pass so
-- calibration reads are O(1) lookups.
CREATE TABLE IF NOT EXISTS fv_backtest_forwards (
  symbol          text        NOT NULL,
  as_of           date        NOT NULL,
  horizon_days    integer     NOT NULL,
  end_px          double precision,
  min_close       double precision,
  n_bars          integer,
  computed_at     timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (symbol, as_of, horizon_days)
);

CREATE INDEX IF NOT EXISTS idx_fv_backtest_forwards_symbol
  ON fv_backtest_forwards (symbol, as_of);

-- nightly refresh at 01:30 UTC (after evening bars land)
insert into job_definitions (name, label, purpose, kind, cron, enabled, depends_on, priority)
values ('fv-backtest', 'FV backtest forward-price refresh',
        'Materialize forward closes for every stored FV run into fv_backtest_forwards in one windowed pass over daily_bars',
        'job', '30 1 * * *', true, null, 30)
on conflict (name) do update set cron=excluded.cron, purpose=excluded.purpose,
       priority=excluded.priority;
