-- Crash-alpha snapshots — version the daily PUT_ENTRY / CAPITULATION
-- scores so the signals can be graded against realized tape:
--   capitulation_score ≥ threshold  → did SPY bounce in 20d?
--   put candidates flagged          → did those names underperform?
-- One row/day— the evaluator fills realized returns so meta can
-- calibrate the thresholds instead of trusting the heuristic.
CREATE TABLE IF NOT EXISTS crash_alpha_snapshots (
    id                bigserial PRIMARY KEY,
    as_of             date NOT NULL UNIQUE,
    capitulation_score int,
    cap_tier          text,                -- none | watch | cap_zone | capitulating
    put_candidates    jsonb,               -- [{symbol, score, rsi, ext200, ...}]
    spy_vs_200        double precision,
    vix               double precision,
    pct_above_50      double precision,    -- breadth internals at the read
    pct_20d_low       double precision,
    pct_washed        double precision,    -- % universe in capitulation/knife
    dip_character     text,
    payload           jsonb,
    spy_ret_20d       double precision,    -- graded: realized SPY fwd ret %
    spy_ret_60d       double precision,
    cap_bounce        boolean,             -- cap≥60 && spy_ret_20d > +2%?
    put_hit_rate      double precision,    -- % of candidates down in 20d
    graded_at         timestamptz,
    created_at        timestamptz DEFAULT now()
);
CREATE INDEX IF NOT EXISTS crash_alpha_date_idx
    ON crash_alpha_snapshots (as_of DESC);
