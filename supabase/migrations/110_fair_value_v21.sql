-- 110_fair_value_v21.sql — fair-value engine v2.1.
-- Extends the append-only fair_value_v2_runs journal with the fields
-- needed for training/calibration and downstream display:
--   expected_fair_value — probability-weighted Σ p·scenario FV
--   spot_at_run         — price at run time (provenance for return labels;
--                         NOT a valuation input)
--   quality_flags       — ordering_violation / scenarios_incomplete /
--                         stale_input_rejected / extreme_gap / no_scenarios
-- The view is recreated so consumers pick the new columns up unchanged.

ALTER TABLE fair_value_v2_runs
    ADD COLUMN IF NOT EXISTS expected_fair_value double precision,
    ADD COLUMN IF NOT EXISTS spot_at_run          double precision,
    ADD COLUMN IF NOT EXISTS quality_flags        jsonb;

CREATE INDEX IF NOT EXISTS fair_value_v2_runs_symbol_asof
    ON fair_value_v2_runs (symbol, as_of);

DROP VIEW IF EXISTS symbol_fair_values;
CREATE VIEW symbol_fair_values AS
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
    created_at
FROM fair_value_v2_runs
ORDER BY symbol, as_of DESC;
