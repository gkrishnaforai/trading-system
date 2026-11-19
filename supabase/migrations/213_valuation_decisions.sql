-- Valuation decisions — quality × priced-in matrix + thesis integrity
-- + entry/trim/exit bands, journaled daily per symbol. Advisory only.
-- Preserves original assumptions per row (Phase-3 grading contract):
-- new (symbol, as_of) rows, never in-place updates of prior days.
CREATE TABLE IF NOT EXISTS valuation_decisions (
    id                        BIGSERIAL PRIMARY KEY,
    symbol                    TEXT NOT NULL,
    as_of                     DATE NOT NULL,
    business_quality          NUMERIC,             -- 0-100 eq+gq+fw composite
    priced_in_attractiveness  NUMERIC,             -- 100 − priced-in score
    thesis_integrity          TEXT,                -- intact|watch|deteriorating|broken
    integrity_evidence        JSONB DEFAULT '[]'::jsonb,
    quadrant                  TEXT,                -- accumulate|hold_wait_pullback|...
    band                      TEXT,                -- entry_zone|at_bull|below_bear_intact|thesis_review|...
    decision                  TEXT,                -- enter|hold|trim|exit_review|exit_core_review|reassess|wait|avoid
    decision_reasons          JSONB DEFAULT '[]'::jsonb,
    risk_flags                JSONB DEFAULT '[]'::jsonb,
    price                     NUMERIC,
    fv_bear                   NUMERIC,
    fv_base                   NUMERIC,
    fv_bull                   NUMERIC,
    entry_zone                NUMERIC,             -- fv_base × (1−mos_required)
    mos_required              NUMERIC,             -- clamp(0.15+0.20×disp,15,30%)
    expectation_gap           NUMERIC,
    compression_drag          NUMERIC,
    model_version             TEXT,
    missing_inputs            JSONB DEFAULT '[]'::jsonb,
    detail                    JSONB,
    created_at                TIMESTAMPTZ DEFAULT now(),
    UNIQUE (symbol, as_of)
);
CREATE INDEX IF NOT EXISTS idx_valdec_symbol_date
    ON valuation_decisions (symbol, as_of DESC);
CREATE INDEX IF NOT EXISTS idx_valdec_decision
    ON valuation_decisions (decision, as_of DESC);
