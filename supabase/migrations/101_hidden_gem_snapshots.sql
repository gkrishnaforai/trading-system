-- Hidden Gems daily journal — the change column (NEW/↑/↓/REMOVED)
-- diff's today vs yesterday— forward grading joins make the spec's
-- "does EPS acceleration actually predict returns" a testable query.
CREATE TABLE IF NOT EXISTS hidden_gem_snapshots (
    id         bigserial PRIMARY KEY,
    snap_date  date NOT NULL,
    symbol     text NOT NULL,
    engine_version text,              -- gems_v1, v2... version-vs-version perf
    score      double precision,      -- final 0-125
    core       double precision,      -- 0-100 weighted core
    bonus      double precision,      -- hidden-gem bonus 0-25
    aligned    int,                   -- arrows firing (7 = full)
    valuation  text,                  -- reasonable|elevated|extreme
    momentum   text,                  -- momentum_state at snapshot
    parts      jsonb,                 -- per-factor sub-scores
    -- graded later: was the call right?
    ret_20d    double precision,
    ret_60d    double precision,
    vs_spy_20d double precision,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (snap_date, symbol)
);
CREATE INDEX IF NOT EXISTS hidden_gem_date_idx
    ON hidden_gem_snapshots (snap_date DESC);
CREATE INDEX IF NOT EXISTS hidden_gem_sym_idx
    ON hidden_gem_snapshots (symbol, snap_date DESC);
