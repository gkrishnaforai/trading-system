-- 219_index_valuation.sql — market-level valuation journal.
--
-- One row per day: index ETF trailing P/Es (Yahoo), the
-- cap-weighted forward P/E of the estimate-covered universe, the
-- earnings-yield vs 10Y spread (the equity-risk-premium proxy), and
-- the verdict tier + plain-English/technical text so the regime card
-- can say "too pricey / fair / cheap" in both registers. Rows accrue
-- the percentile window — the endpoint reports obs count so a short
-- window is never implied to be all-time context.
--
-- Idempotent on as_of — an intraday re-run updates the row.

CREATE TABLE IF NOT EXISTS index_valuation_daily (
    as_of                    DATE PRIMARY KEY,
    spy_pe_trailing          NUMERIC,
    qqq_pe_trailing          NUMERIC,
    tracked_fwd_pe           NUMERIC,
    tracked_names            INTEGER,
    tracked_cap_usd          NUMERIC,
    tracked_ey_pct           NUMERIC,
    tnx_yield_pct            NUMERIC,
    ey_spread_pp             NUMERIC,        -- tracked EY − 10Y
    verdict                  TEXT,           -- deep/healthy/thin/negative_premium
    verdict_tone             TEXT,           -- ok / warn / bad
    headline                 TEXT,           -- plain-English read
    detail                   TEXT,           -- technical decomposition
    raw                      JSONB,
    created_at               TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_index_valuation_asof
    ON index_valuation_daily (as_of DESC);

-- schedule — after fred-macro (13:10 UTC) so the day's 10Y lands in
-- macro_market_data before the spread is computed; before the card
-- reads it in the morning ET window.
UPDATE job_definitions
SET cron = '45 13 * * 1-5',
    enabled = true,
    depends_on = ARRAY['fred-macro']::text[],
    updated_at = now()
WHERE name = 'index-valuation';
