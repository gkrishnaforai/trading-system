-- User-supplied fair-value overrides for cases where the system-generated
-- value is wrong or unreasonable (bad data, wrong category routing, missing
-- context the model cannot see). Overrides win over engine runs everywhere:
-- the resolver returns them, and symbol_fair_values projects them.
--
-- Lifecycle: upsert per symbol; enabled=false or expires_at < now() deactivates
-- without deleting history. The append-only run history is untouched — engine
-- runs keep recording what the model would have said during the override.
CREATE TABLE IF NOT EXISTS fair_value_overrides (
    symbol            VARCHAR(32) PRIMARY KEY,
    fair_value        DOUBLE PRECISION NOT NULL,
    bear_fair_value   DOUBLE PRECISION,
    bull_fair_value   DOUBLE PRECISION,
    regime            VARCHAR(100),
    reason            TEXT,
    updated_by        VARCHAR(100),
    enabled           BOOLEAN NOT NULL DEFAULT TRUE,
    expires_at        TIMESTAMPTZ,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_fv_overrides_enabled ON fair_value_overrides(enabled);

-- Recreate the latest-state projection so overrides take precedence while
-- preserving the run provenance underneath. model_version reports
-- 'user_override' when an override is supplying the value. Drop first —
-- CREATE OR REPLACE cannot change column types.
DROP VIEW IF EXISTS symbol_fair_values;
CREATE VIEW symbol_fair_values AS
WITH latest AS (
    SELECT DISTINCT ON (symbol)
        symbol, run_id, as_of, inputs_watermark, features_hash,
        fair_value, scenario_fair_values, regime, model_version, created_at
    FROM fair_value_v2_runs
    ORDER BY symbol, as_of DESC
), active_overrides AS (
    SELECT *
    FROM fair_value_overrides
    WHERE enabled = TRUE
      AND (expires_at IS NULL OR expires_at > now())
)
SELECT
    l.symbol,
    l.run_id,
    COALESCE(o.updated_at, l.as_of) AS as_of,
    l.inputs_watermark,
    l.features_hash,
    COALESCE(o.fair_value, l.fair_value) AS fair_value,
    CASE
        WHEN o.symbol IS NOT NULL
             AND (o.bear_fair_value IS NOT NULL OR o.bull_fair_value IS NOT NULL)
        THEN jsonb_build_object('bear', o.bear_fair_value, 'bull', o.bull_fair_value)
        ELSE l.scenario_fair_values
    END AS scenario_fair_values,
    COALESCE(o.regime, l.regime) AS regime,
    CASE WHEN o.symbol IS NOT NULL THEN 'user_override' ELSE l.model_version END AS model_version,
    COALESCE(o.updated_at, l.created_at) AS created_at
FROM latest l
LEFT JOIN active_overrides o ON o.symbol = l.symbol

UNION ALL

SELECT
    o.symbol,
    NULL AS run_id,
    o.updated_at AS as_of,
    NULL AS inputs_watermark,
    NULL AS features_hash,
    o.fair_value,
    CASE
        WHEN o.bear_fair_value IS NOT NULL OR o.bull_fair_value IS NOT NULL
        THEN jsonb_build_object('bear', o.bear_fair_value, 'bull', o.bull_fair_value)
        ELSE NULL
    END AS scenario_fair_values,
    o.regime,
    'user_override' AS model_version,
    o.updated_at AS created_at
FROM active_overrides o
WHERE NOT EXISTS (SELECT 1 FROM latest l WHERE l.symbol = o.symbol);
