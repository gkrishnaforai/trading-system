-- 125_forward_growth.sql — Forward Growth Intelligence flags + persistence
--
-- Flags live on stocks (same surface as fundamental_state/momentum_state —
-- every screener/card/pulse already queries it):
--   revision_score / revision_grade   street estimate-revision momentum
--                                     (SA-quant-style, but honest about
--                                     thin coverage and sign-flip bases)
--   priced_status                     how much forward growth the price
--                                     already capitalizes (lt_power curve
--                                     when present, FV upside fallback)
--   emerging_growth                   product-ramp uplift tier from
--                                     scenario-bucketed initiatives
--   fwd_detail                        jsonb inputs behind all three flags
--
-- Evidence ledger gets the richer claim schema and the forecast
-- snapshot/actual tables form the calibration harness.

ALTER TABLE stocks
    ADD COLUMN IF NOT EXISTS revision_score numeric,
    ADD COLUMN IF NOT EXISTS revision_grade text,
    ADD COLUMN IF NOT EXISTS priced_status text,
    ADD COLUMN IF NOT EXISTS emerging_growth text,
    ADD COLUMN IF NOT EXISTS fwd_detail jsonb;

CREATE INDEX IF NOT EXISTS idx_stocks_revision_grade
    ON stocks (revision_grade) WHERE revision_grade IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_stocks_priced_status
    ON stocks (priced_status) WHERE priced_status IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_stocks_emerging_growth
    ON stocks (emerging_growth) WHERE emerging_growth IS NOT NULL;

-- ---------- evidence ledger: richer claim schema ----------
ALTER TABLE tailwinds
    ADD COLUMN IF NOT EXISTS commercial_stage text,
        -- concept | development | qualification | ramp | production
    ADD COLUMN IF NOT EXISTS financial_horizon text,
        -- this_year | 1_to_3_years | 3_plus_years
    ADD COLUMN IF NOT EXISTS expected_impact jsonb,
        -- {revenue: pos|neg|uncertain, gross_margin: ..., eps: ...}
    ADD COLUMN IF NOT EXISTS verification_status text DEFAULT 'unverified',
        -- unverified | corroborated | confirmed | contradicted
    ADD COLUMN IF NOT EXISTS next_milestone text,
    ADD COLUMN IF NOT EXISTS expires_at date;

-- ---------- product & segment intelligence ----------
CREATE TABLE IF NOT EXISTS company_segments (
    id              bigserial PRIMARY KEY,
    symbol          text NOT NULL,
    segment         text NOT NULL,
    period          text NOT NULL,          -- e.g. FY2025, FY2026Q2
    revenue         numeric,
    gross_profit    numeric,
    growth_yoy      numeric,
    source          text,                   -- provider | filing | manual
    as_of           date NOT NULL,
    created_at      timestamptz DEFAULT now(),
    UNIQUE (symbol, segment, period)
);

CREATE TABLE IF NOT EXISTS product_initiatives (
    id              bigserial PRIMARY KEY,
    symbol          text NOT NULL,
    name            text NOT NULL,          -- 'data-center power products'
    channel         text,                   -- tailwinds channel link
    segment         text,
    stage           text NOT NULL,          -- concept|development|qualification|ramp|production
    addressable_band text,                  -- e.g. '0.5-2B' qualitative
    scenario_buckets jsonb,                 -- {fy_plus_1:{bear,base,bull}, fy_plus_3:{...}} revenue $
    incr_margin     numeric,                -- incremental operating margin assumption
    confidence      numeric,                -- 0-1
    evidence        jsonb,                  -- [{source, published_at, claim}]
    status          text DEFAULT 'active',  -- active | dead | realized
    created_at      timestamptz DEFAULT now(),
    updated_at      timestamptz DEFAULT now(),
    UNIQUE (symbol, name)
);

-- ---------- calibration harness ----------
CREATE TABLE IF NOT EXISTS growth_forecast_snapshots (
    id              bigserial PRIMARY KEY,
    symbol          text NOT NULL,
    as_of           date NOT NULL,
    model_version   text NOT NULL,
    -- consensus-side view (the street's forecast at snapshot time)
    fwd_eps_avg     numeric,
    fwd_rev_avg     numeric,
    est_revision_pct numeric,
    rev_breadth_30d int,
    revision_score  numeric,
    revision_grade  text,
    num_analysts    int,
    -- our-side view (what the engines believed that day)
    fundamental_state text,
    priced_status   text,
    emerging_growth text,
    fwd_rev_uplift_fy1 numeric,             -- Σ product ramps, $ by horizon
    fwd_rev_uplift_fy3 numeric,
    detail          jsonb,                  -- scenario buckets, inputs, flags
    prev_id         bigint,                 -- chain to prior snapshot
    created_at      timestamptz DEFAULT now(),
    UNIQUE (symbol, as_of, model_version)
);
CREATE INDEX IF NOT EXISTS idx_gfs_symbol ON growth_forecast_snapshots (symbol, as_of);

CREATE TABLE IF NOT EXISTS forecast_actuals (
    id              bigserial PRIMARY KEY,
    symbol          text NOT NULL,
    snapshot_id     bigint REFERENCES growth_forecast_snapshots(id),
    metric          text NOT NULL,          -- est_revision_pct | rev_growth | eps_growth
    horizon_days    int NOT NULL,
    forecast        numeric,
    actual          numeric,
    error           numeric,
    graded_at       timestamptz DEFAULT now(),
    UNIQUE (snapshot_id, metric, horizon_days)
);

COMMENT ON TABLE growth_forecast_snapshots IS
'Point-in-time forward view — answers "what did the engine believe about
X growth on date Y, with what evidence". Feeds forecast_actuals for
walk-forward calibration. Never COALESCE-forwarded.';
