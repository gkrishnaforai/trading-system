-- Growth priced-in daily journal — the inverse metrics over FV runs.
-- required CAGR under our exit multiple, forecast-vs-required gap,
-- multiple-compression drag, bear/base/bull bands, priced-in score.
-- Preserves the original assumptions at write time (spec Phase-3
-- grading contract): never update growth inputs in place, always a
-- new (symbol, as_of) row. inputs live in `detail` for reproducibility.
CREATE TABLE IF NOT EXISTS growth_priced_in_daily (
    id                    BIGSERIAL PRIMARY KEY,
    symbol                TEXT NOT NULL,
    as_of                 DATE NOT NULL,
    run_id                TEXT,                    -- provenance → fv run
    price                 NUMERIC,
    eps_fwd               NUMERIC,
    exit_pe               NUMERIC,                 -- engine's own justified PE
    pe_now                NUMERIC,
    forecast_cagr         NUMERIC,                 -- analyst or labeled proxy
    forecast_src          TEXT,
    required_cagr         NUMERIC,                 -- growth the price demands
    implied_growth        NUMERIC,                 -- reverse-DCF triangulation
    implied_status        TEXT,                    -- valid|negative_fcf|...
    expectation_gap       NUMERIC,                 -- forecast − required (pp)
    compression_drag      NUMERIC,                 -- annualized mult. cost
    expected_annual_return NUMERIC,                -- run's own 2y total
    fv_bear               NUMERIC,
    fv_base               NUMERIC,
    fv_bull               NUMERIC,
    valuation_dispersion  NUMERIC,                 -- (bull−bear)/base
    margin_of_safety      NUMERIC,
    score                 NUMERIC,                 -- 0-100 priced-in-ness
    model_version         TEXT,
    missing_inputs        JSONB DEFAULT '[]'::jsonb,
    detail                JSONB,                   -- full row incl inputs
    created_at            TIMESTAMPTZ DEFAULT now(),
    UNIQUE (symbol, as_of)
);
CREATE INDEX IF NOT EXISTS idx_gpi_symbol_date
    ON growth_priced_in_daily (symbol, as_of DESC);
CREATE INDEX IF NOT EXISTS idx_gpi_date
    ON growth_priced_in_daily (as_of DESC);
