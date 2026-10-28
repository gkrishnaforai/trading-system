-- 164_credit_health_snapshots.sql — canonical market-credit block.
-- One journaled row per day: FRED spread inputs (point-in-time via
-- fred_asof, NOT the snapshot date), ETF corroboration read from the
-- regime payload, the raw classifier state and the post-hysteresis
-- effective state. raw vs effective stay separate — hysteresis is a
-- policy overlay on the evidence, not a rewrite of it. Backfill
-- replays FRED history so posture grading sees what credit said on
-- each historical as_of — never today's knowledge on a past date.
CREATE TABLE IF NOT EXISTS credit_health_snapshots (
    as_of            date PRIMARY KEY,
    fred_asof        date,             -- last FRED observation used
    hy_oas           numeric,          -- BAMLH0A0HYM2 level
    hy_oas_d5        numeric,          -- 5-obs change, points
    hy_oas_d20       numeric,          -- 20-obs change, points
    ig_oas           numeric,          -- BAMLC0A0CM level
    ig_oas_d20       numeric,          -- 20-obs change, points
    hyg_lqd_5d       numeric,          -- ETF confirms from regime payload
    hyg_lqd_20d      numeric,
    hyg_ief_20d      numeric,
    raw_state        text NOT NULL,    -- classifier output, pre-hysteresis
    credit_state     text NOT NULL,    -- effective state post-hysteresis
    days_in_state    int,
    confidence       text NOT NULL,    -- high|medium|low
    stale_days       int,              -- days since fred_asof
    below_run        int,              -- distinct obs ≤ caution while severe
    why              text,
    created_at       timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_chs_fred_asof
    ON credit_health_snapshots (fred_asof);
CREATE INDEX IF NOT EXISTS idx_chs_state
    ON credit_health_snapshots (credit_state);
