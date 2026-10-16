-- Conviction List daily journal — the meta-engine nightly pick.
-- Every row is a point-in-time "best idea" so performance review is
-- a query: which daily/weekly/monthly picks actually paid, and is
-- watch (expensive early compounders) outperforming deploy?
CREATE TABLE IF NOT EXISTS conviction_snapshots (
    id             bigserial PRIMARY KEY,
    snap_date      date NOT NULL,
    symbol         text NOT NULL,
    rank           int,
    score          double precision,   -- 0-100 five-leg composite
    lane           text,               -- deploy | watch | off
    parts          jsonb,              -- growth/quality/tape/consensus
                                       -- /theme_money sub-scores
    sources        jsonb,              -- which engines surfaced it
    n_sources      int,
    theme          text,
    theme_score    double precision,
    fwd_pe         double precision,
    valuation      text,               -- reasonable|elevated|extreme
    momentum_state text,
    dd52w          double precision,   -- distance off 52w high
    daily_pick     boolean,            -- today best-2
    future_score   double precision,   -- 0-95 future-compounder:
                                       -- thesis exposure + evidence
                                       -- + headroom (ranks watch)
    weekly_pick    boolean,            -- Friday rollup winner
    monthly_pick   boolean,            -- month-end top-2 for next mo
    -- graded later:
    ret_5d         double precision,
    ret_20d        double precision,
    ret_60d        double precision,
    vs_spy_20d     double precision,
    engine_version text,
    created_at     timestamptz NOT NULL DEFAULT now(),
    UNIQUE (snap_date, symbol)
);
CREATE INDEX IF NOT EXISTS conv_snap_date_idx
    ON conviction_snapshots (snap_date DESC);
CREATE INDEX IF NOT EXISTS conv_snap_sym_idx
    ON conviction_snapshots (symbol, snap_date DESC);
