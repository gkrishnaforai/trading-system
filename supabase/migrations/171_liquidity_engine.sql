-- 171_liquidity_engine.sql — Liquidity & new-money flow monitor.
--
-- Distinct from the macro_engine 'liquidity' module (M2 YoY only —
-- broad money, not equity-bound liquidity). This tracks the
-- transmission chain: Fed balance sheet → TGA/RRP/reserves → bank
-- credit → financial conditions → equity participation.
--
-- liquidity_snapshots: weekly journaled state — score + band +
-- direction/acceleration/transmission + per-component detail and
-- each FRED series' observation_date (PIT: a replay sees what was
-- actually published, not today's revised view).

SELECT pg_advisory_xact_lock(715171);

CREATE TABLE IF NOT EXISTS liquidity_snapshots (
    id            bigserial PRIMARY KEY,
    as_of         date NOT NULL UNIQUE,
    score         int,
    band          text,          -- strong_expansion..severe
    direction     text,          -- improving|neutral|deteriorating
    acceleration  text,          -- accelerating|stable|decelerating
    transmission  text,          -- strong|moderate|weak (to equities)
    components    jsonb,         -- per-component score + change + series
    impulses      jsonb,         -- fed/treasury/rrp/credit/conditions/flows
    payload       jsonb,         -- full state incl. obs_dates + breadth
    created_at    timestamptz DEFAULT now()
);

-- weekly — WALCL/WRESBAL/WTREGEN print weekly (Wed/Fri), so Saturday
-- has the complete print before the Sunday research pass reads it.
INSERT INTO job_definitions (name, label, purpose, cron, enabled,
                             depends_on, dep_max_age_h, cooldown_min,
                             priority)
VALUES ('liquidity', 'Liquidity & new-money flow',
        'Fed BS/TGA/RRP/reserves + credit + equity-transmission →'
        ' 0-100 impulse score, journaled',
        '0 14 * * 6', true, '{momentum}', 96, 60, 60)
ON CONFLICT (name) DO NOTHING;
