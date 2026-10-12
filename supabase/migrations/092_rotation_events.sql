-- Rotation events — journal each day the flow classifier fires a
-- theme rotation (A→outflow while B flips rotating_in/inflow), so the
-- forward edge gets graded per-pair instead of trusted on priors.
-- One row per event; the evaluator fills rel_10/20/40d and hit flags.
CREATE TABLE IF NOT EXISTS rotation_events (
    id            bigserial PRIMARY KEY,
    as_of         date NOT NULL,
    from_etf      text NOT NULL,
    to_etf        text NOT NULL,
    to_flow       text,                    -- rotating_in | inflow
    from_r20      double precision,
    to_r20        double precision,
    rel_10d       double precision,        -- graded: to − from fwd ret
    rel_20d       double precision,
    rel_40d       double precision,
    to_vs_spy_20d double precision,        -- to-ETF vs SPY at 20d
    to_money5     double precision,        -- signed 5d volume share -1..+1
    to_vol_ratio  double precision,        -- 5d avg vol / 20d avg vol
    vol_confirmed boolean,                 -- money in to B + out of A
    graded_at     timestamptz,
    created_at    timestamptz DEFAULT now(),
    UNIQUE (as_of, from_etf, to_etf)
);
CREATE INDEX IF NOT EXISTS rotation_events_date_idx
    ON rotation_events (as_of DESC);

-- idempotent adds for the volume-confirmation columns (post-first-run)
ALTER TABLE rotation_events
    ADD COLUMN IF NOT EXISTS to_money5 double precision,
    ADD COLUMN IF NOT EXISTS to_vol_ratio double precision,
    ADD COLUMN IF NOT EXISTS vol_confirmed boolean;
