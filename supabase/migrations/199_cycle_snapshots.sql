-- 199_cycle_snapshots.sql — AI Cycle Rotation Tracker journal.
-- One row per (symbol, evidence quarter, run date): the 8-component
-- cycle score, three-peak state, demand-peak window (range, never a
-- point), revenue-peak risk and the policy decision. Append-only —
-- quarter-over-quarter movement compares rows across quarter_label,
-- never updates prior evidence.
SELECT pg_advisory_xact_lock(715199);

CREATE TABLE IF NOT EXISTS cycle_snapshots (
    id                bigserial PRIMARY KEY,
    symbol            text NOT NULL,
    quarter_label     text NOT NULL,       -- '2026Q4' — evidence period
    as_of             date NOT NULL,
    cohort            text,
    composite         numeric,             -- 0-100, coverage-weighted
    coverage_pct      numeric,             -- share of the 100 pts scored
    demand_accel        numeric,           -- 20
    backlog_quality     numeric,           -- 15
    est_revisions       numeric,           -- 15
    margin_cf           numeric,           -- 15
    capacity_util       numeric,           -- 10
    customer_adoption   numeric,           -- 10
    capital_recovery    numeric,           -- 10
    valuation_duration  numeric,           -- 5
    -- three-peak detection — NULL = can't tell, never false-by-default
    order_peak        boolean,             -- peak 1: demand/orders rolled
    estimate_peak     boolean,             -- peak 2: expectations rolled
    revenue_peak      boolean,             -- peak 3: reported growth rolled
    -- demand-peak window — a year RANGE, not a point
    demand_peak_lo    smallint,
    demand_peak_hi    smallint,
    peak_confidence   text,                -- high | medium | low
    peak_source       text,                -- claim id | cohort_seed
    peak_movement     text,                -- pulled_forward | pushed_out
                                           -- | unchanged | new
    quarters_to_peak  smallint,            -- from peak_lo (conservative)
    rev_peak_risk     numeric,             -- 0-100 deterministic
    -- decision layer
    decision          text,                -- accumulate | add_on_pullback
                                           -- | hold | trim | exit
                                           -- | research_incomplete
    structural_break  boolean,
    valuation_blocked boolean,
    components        jsonb NOT NULL DEFAULT '{}',   -- leg detail + notes
    peaks             jsonb NOT NULL DEFAULT '{}',   -- peak basis detail
    decision_detail   jsonb NOT NULL DEFAULT '{}',   -- fired rule + ctx
    flags             jsonb NOT NULL DEFAULT '[]',
    rules_version     text,
    created_at        timestamptz NOT NULL DEFAULT now(),
    UNIQUE (symbol, quarter_label, as_of)
);

CREATE INDEX IF NOT EXISTS idx_cycle_sym_q
    ON cycle_snapshots (symbol, quarter_label, as_of DESC);
CREATE INDEX IF NOT EXISTS idx_cycle_decision
    ON cycle_snapshots (decision, quarter_label);
CREATE INDEX IF NOT EXISTS idx_cycle_cohort
    ON cycle_snapshots (cohort, quarter_label);

-- Weekly cadence — quarter_label keys the evidence period so more
-- frequent runs append without overwriting quarters. Post-earnings
-- refreshes land in the same quarter_label naturally.
INSERT INTO job_definitions (name, label, cron, enabled, cooldown_min,
                             priority)
VALUES ('ai-cycle', 'AI cycle rotation tracker (weekly)',
        '30 6 * * 6', true, 720, 40)
ON CONFLICT (name) DO UPDATE SET
    cron         = COALESCE(job_definitions.cron, EXCLUDED.cron),
    enabled      = CASE WHEN job_definitions.cron IS NULL
                        THEN EXCLUDED.enabled
                        ELSE job_definitions.enabled END,
    priority     = EXCLUDED.priority;
