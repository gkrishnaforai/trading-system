-- 215 — driver_bridge: scenario drivers with provenance + the
-- collapsed forecast they produce, and schedules for the
-- expectations-engine jobs.

CREATE TABLE IF NOT EXISTS driver_assumptions (
    id               BIGSERIAL PRIMARY KEY,
    symbol           TEXT NOT NULL,
    scenario         TEXT NOT NULL
                     CHECK (scenario IN ('bear','base','bull')),
    driver_key       TEXT NOT NULL,        -- 'revenue_growth' | 'op_margin' | …
    value            DOUBLE PRECISION,
    unit             TEXT,                 -- 'fraction' | 'usd' | 'count' | 'pct'
    period           TEXT,                 -- 'FY27' | 'Q4-26' | 'TTM' …
    assumption_type  TEXT NOT NULL
                     CHECK (assumption_type IN
                        ('reported_fact','management_guidance',
                         'analyst_estimate','industry_research',
                         'model_assumption')),
    rationale_claim_id TEXT,               -- NULL ⇒ must be model_assumption
    confidence       DOUBLE PRECISION,     -- forecast confidence 0-1
    source_ref       JSONB,                -- {table, id} of the journal row
    as_of            DATE NOT NULL DEFAULT current_date,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (symbol, scenario, driver_key, period, as_of)
);
CREATE INDEX IF NOT EXISTS idx_dassump_symbol
    ON driver_assumptions (symbol, as_of DESC);
CREATE INDEX IF NOT EXISTS idx_dassump_claim
    ON driver_assumptions (rationale_claim_id)
    WHERE rationale_claim_id IS NOT NULL;

CREATE TABLE IF NOT EXISTS driver_forecasts (
    id             BIGSERIAL PRIMARY KEY,
    symbol         TEXT NOT NULL,
    as_of          DATE NOT NULL DEFAULT current_date,
    regime         TEXT,
    forecast       JSONB NOT NULL,         -- collapsed bear/base/bull scalars
    provenance     JSONB,                  -- claim ids behind each leg
    missing_inputs JSONB,
    coverage       DOUBLE PRECISION,       -- share of catalog drivers supplied
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (symbol, as_of)
);
CREATE INDEX IF NOT EXISTS idx_dforecast_symbol
    ON driver_forecasts (symbol, as_of DESC);

ALTER TABLE growth_priced_in_daily
    ADD COLUMN IF NOT EXISTS driver_forecast JSONB;

-- the expectations-engine jobs exist in the catalog (registered on
-- deploy) but ship unscheduled — wire them into the nightly chain:
-- flywheel 0:22 → earnings-quality 15:22 → priced-in 30:22 →
-- valuation-decision 45:22 (depends on a same-day priced-in run) →
-- narrative-claims 50:22 (no hard deps — its collectors degrade
-- gracefully on stale sources).
UPDATE job_definitions SET
    cron='30 22 * * 1-5', enabled=true, timeout_s=900, cooldown_min=60
    WHERE name='priced-in';
UPDATE job_definitions SET
    cron='45 22 * * 1-5', enabled=true, timeout_s=900, cooldown_min=60,
    depends_on='{priced-in}', dep_max_age_h=8
    WHERE name='valuation-decision';
UPDATE job_definitions SET
    cron='50 22 * * 1-5', enabled=true, timeout_s=1800, cooldown_min=60
    WHERE name='narrative-claims';
UPDATE job_definitions SET
    cron='55 22 * * 1-5', enabled=true, timeout_s=900, cooldown_min=60,
    depends_on='{narrative-claims}', dep_max_age_h=8
    WHERE name='driver-bridge';
