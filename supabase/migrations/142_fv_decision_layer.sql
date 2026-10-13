-- Fair-value decision layer — FV is worth, buy_below is the price
-- decision jsonb carries the full payload (mos adders, risk flags,
-- fv_reference); the flat columns keep consumers on simple reads

ALTER TABLE fair_value_v2_runs
    ADD COLUMN IF NOT EXISTS decision jsonb,
    ADD COLUMN IF NOT EXISTS buy_below double precision,
    ADD COLUMN IF NOT EXISTS valuation_confidence text,
    ADD COLUMN IF NOT EXISTS expected_return_2y double precision,
    ADD COLUMN IF NOT EXISTS fv_upside_pct double precision;

-- new columns must append at the end for CREATE OR REPLACE VIEW
CREATE OR REPLACE VIEW symbol_fair_values AS
SELECT DISTINCT ON (symbol)
    symbol,
    run_id,
    as_of,
    inputs_watermark,
    features_hash,
    fair_value,
    scenario_fair_values,
    expected_fair_value,
    spot_at_run,
    quality_flags,
    regime,
    model_version,
    created_at,
    buy_below,
    valuation_confidence,
    expected_return_2y,
    fv_upside_pct,
    decision
FROM fair_value_v2_runs
ORDER BY symbol, as_of DESC;
