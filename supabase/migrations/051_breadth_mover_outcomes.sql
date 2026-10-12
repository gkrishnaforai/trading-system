-- 051_breadth_mover_outcomes.sql
-- History-derived signals:
--   screen_runs.breadth — per-run regime census (% uptrend/downtrend, new
--     entries, vs prior run) so breadth trends accumulate cheaply.
--   mover_outcomes      — forward returns after each movers-list snapshot,
--     the honesty loop for the quality verdict + accumulation flag.

ALTER TABLE screen_runs ADD COLUMN IF NOT EXISTS breadth jsonb;

-- Persist the streak verdict on the snapshot row itself — computed post-save
-- today, so it lives only in the response; storing it makes the stats view
-- and future diffs possible.
ALTER TABLE mover_snapshots ADD COLUMN IF NOT EXISTS days_on_list integer;
ALTER TABLE mover_snapshots ADD COLUMN IF NOT EXISTS accumulation boolean NOT NULL DEFAULT false;

CREATE TABLE IF NOT EXISTS mover_outcomes (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    symbol        varchar(32) NOT NULL,
    as_of_date    date        NOT NULL,
    horizon_days  integer NOT NULL,
    entry_price   numeric,
    ret_pct       numeric,
    mfe_pct       numeric,
    mae_pct       numeric,
    evaluated_at  timestamptz NOT NULL DEFAULT now(),
    UNIQUE (symbol, as_of_date, horizon_days)
);

CREATE INDEX IF NOT EXISTS idx_mover_outcomes_sym_date
    ON mover_outcomes (symbol, as_of_date);

-- Did the verdict / accumulation flag predict? Rollup by verdict × horizon,
-- with accumulation split — verdicts that don't beat 'fails quality gate'
-- get their gate re-thought.
CREATE OR REPLACE VIEW mover_stats AS
SELECT s.verdict,
       s.accumulation,
       o.horizon_days,
       count(*) AS n,
       round(avg(o.ret_pct)::numeric, 2) AS avg_ret_pct,
       round(avg(o.mfe_pct)::numeric, 2) AS avg_mfe_pct,
       round(avg(o.mae_pct)::numeric, 2) AS avg_mae_pct,
       round(avg(CASE WHEN o.ret_pct > 0 THEN 1.0 ELSE 0.0 END)::numeric, 3) AS win_rate,
       max(s.as_of_date) AS last_seen
FROM mover_outcomes o
JOIN mover_snapshots s
  ON s.symbol = o.symbol AND s.as_of_date = o.as_of_date
GROUP BY s.verdict, s.accumulation, o.horizon_days;
