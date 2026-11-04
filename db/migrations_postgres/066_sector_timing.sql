-- sector_timing_daily: per-sector two-score state machine —
-- bottom opportunity vs rebound confirmation, kept separate so
-- 'cheap' and 'recovering' never conflate into one number.
CREATE TABLE IF NOT EXISTS sector_timing_daily (
    as_of          DATE NOT NULL,
    sector_key     TEXT NOT NULL,
    etf            TEXT,
    opp_score      DOUBLE PRECISION,
    conf_score     DOUBLE PRECISION,
    trap_score     DOUBLE PRECISION,
    state          TEXT,
    signals        JSONB NOT NULL DEFAULT '{}',
    missing        JSONB NOT NULL DEFAULT '[]',
    computed_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (as_of, sector_key)
);
