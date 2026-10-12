-- Versioned fair-value v2 run results with an inputs watermark.
-- The watermark is the newest timestamp observed across the data sources that
-- feed valuation inputs (fundamentals snapshots, statements, consensus,
-- estimates, category overrides, macro). A stored run is reused while no input
-- is newer than its watermark; live price never invalidates because fair value
-- is price-independent.
CREATE TABLE IF NOT EXISTS fair_value_v2_runs (
    run_id VARCHAR(64) PRIMARY KEY,
    symbol VARCHAR(32) NOT NULL,
    as_of TIMESTAMPTZ NOT NULL,
    inputs_watermark TIMESTAMPTZ,
    features_hash VARCHAR(128),
    fair_value DOUBLE PRECISION,
    scenario_fair_values JSONB,
    regime VARCHAR(128),
    method_results JSONB,
    warnings JSONB,
    model_version VARCHAR(64) NOT NULL DEFAULT 'fair_value_v2',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_fair_value_v2_runs_symbol_asof
    ON fair_value_v2_runs(symbol, as_of DESC);
