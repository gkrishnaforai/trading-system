-- Latest fair-value run per symbol, projected from the append-only
-- fair_value_v2_runs history. Read-optimized "current fair value" surface for
-- consumers (holdings, screens, reports). The runs table remains the source of
-- truth and nothing is duplicated or denormalized.
CREATE OR REPLACE VIEW symbol_fair_values AS
SELECT DISTINCT ON (symbol)
    symbol,
    run_id,
    as_of,
    inputs_watermark,
    features_hash,
    fair_value,
    scenario_fair_values,
    regime,
    model_version,
    created_at
FROM fair_value_v2_runs
ORDER BY symbol, as_of DESC;
