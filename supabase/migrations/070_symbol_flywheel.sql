-- 070: symbol_flywheel — the canonical "expectation gap" layer.
-- One row per symbol holding the earnings-flywheel metrics every
-- engine can join on: business acceleration, beat history, forward-
-- estimate revisions, coverage thinness, valuation sanity, and the
-- muted-reaction flag (big beat + small pop = market hasn't repriced).
-- gap_score = composite 0-100; gap_detail carries the components.

CREATE TABLE IF NOT EXISTS symbol_flywheel (
    symbol             varchar(10) PRIMARY KEY REFERENCES stocks(symbol),
    -- business acceleration (Stage 1)
    rev_growth         double precision,   -- latest YoY
    rev_accel          double precision,   -- YoY growth delta vs prior Q
    gm_now             double precision,
    gm_slope           double precision,   -- GM change vs year-ago Q
    eps_growth         double precision,
    eps_accel          double precision,
    -- expectations (Stage 2)
    beat_streak        integer,            -- consecutive EPS beats
    avg_surprise_pct   double precision,   -- avg surprise, last 4 prints
    last_surprise_pct  double precision,
    last_report_date   date,
    fwd_eps_avg        double precision,   -- consensus next-FY EPS
    fwd_rev_avg        double precision,   -- consensus next-FY revenue
    num_analysts       integer,
    est_revision_pct   double precision,   -- fwd EPS vs ~90d-ago snapshot
    fwd_pe             double precision,
    -- the gap
    muted_reaction     boolean,            -- beat >5% & stock move <3%
    gap_score          double precision,   -- composite 0-100
    gap_detail         jsonb NOT NULL DEFAULT '{}',
    as_of              timestamptz NOT NULL DEFAULT now(),
    updated_at         timestamptz NOT NULL DEFAULT now()
);

-- forward-estimate snapshots — revision drift needs history, so every
-- flywheel refresh appends a row; revisions are computed vs ~90d back
CREATE TABLE IF NOT EXISTS symbol_estimate_snapshots (
    id           bigserial,
    symbol       varchar(10) NOT NULL REFERENCES stocks(symbol),
    period_end   date NOT NULL,            -- fiscal period the estimate is for
    eps_avg      double precision,
    eps_low      double precision,
    eps_high     double precision,
    rev_avg      double precision,
    num_analysts integer,
    as_of        date NOT NULL DEFAULT current_date,
    PRIMARY KEY (symbol, period_end, as_of)
);

CREATE INDEX IF NOT EXISTS idx_est_snap_symbol
    ON symbol_estimate_snapshots (symbol, as_of DESC);
