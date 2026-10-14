-- fair_value_v2_runs: persist the reference legs and decision inputs so a
-- reused run round-trips losslessly. Previously reverse_dcf,
-- relative_valuation and decision_scalars were computed at run time, embedded
-- inside the decision JSONB, and silently dropped on reuse (the SELECT never
-- read them and the INSERT never wrote them).

ALTER TABLE fair_value_v2_runs
    ADD COLUMN IF NOT EXISTS reverse_dcf jsonb,
    ADD COLUMN IF NOT EXISTS relative_valuation jsonb,
    ADD COLUMN IF NOT EXISTS decision_scalars jsonb;

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
    decision,
    reverse_dcf,
    relative_valuation,
    decision_scalars
FROM fair_value_v2_runs
ORDER BY symbol, as_of DESC;
