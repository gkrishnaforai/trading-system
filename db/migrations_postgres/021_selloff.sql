-- Selloff Opportunity Engine — journaled scans for grading + audit.
-- One row per symbol per day: what the engine saw, how it classified
-- the drop, the score legs, the gates, and the staged entry plan.
-- The learning loop grades these rows forward (via board_decisions
-- SELLOFF entries) so the score weights get calibrated by evidence.

CREATE TABLE IF NOT EXISTS selloff_candidates (
    id              BIGSERIAL PRIMARY KEY,
    as_of           DATE        NOT NULL,
    market_level    TEXT,                       -- calm / mild / severe
    market_ctx      JSONB,                      -- breadth, vix, spy_5d
    rank            INT,
    symbol          TEXT        NOT NULL,
    sector          TEXT,
    tier            TEXT,                       -- core / ai_infra / durable
    classification  TEXT,                       -- macro_panic, sector_contagion, positioning_unwind, fundamental_repricing, structural_impairment, idiosyncratic_weakness
    score           NUMERIC(5,1),
    score_legs      JSONB,                      -- dislocation/durability/valuation/recovery/catalyst_rr
    tape            JSONB,                      -- ret_5d, rel_5d, dd_60d, vol_ratio, d_sma50, rsi, mom
    fund            JSONB,                      -- fund_state, thesis, fv, fv_upside, est_rev, fcf_margin, rev_growth
    decision        TEXT,                       -- priority / starter / watch / pass / reject
    gates           JSONB,                      -- hard-gate reasons that overrode the score
    entry_plan      JSONB,                      -- staged 25/25/25/25 + invalidation
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (as_of, symbol)
);

CREATE INDEX IF NOT EXISTS selloff_candidates_asof_idx
    ON selloff_candidates (as_of DESC, score DESC);
CREATE INDEX IF NOT EXISTS selloff_candidates_symbol_idx
    ON selloff_candidates (symbol, as_of DESC);
