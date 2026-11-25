-- 231_selloff_review.sql — the selloff learning loop.
--
-- selloff_grades: rebound outcomes for EVERY journaled candidate,
--   not just the published top-10 (board_outcomes already covers
--   those). Progressive fill: 5d shows early, 20d settles the row.
--   Denormalizes the signal-time features (sbd_class, decision,
--   pf_gap, session-entry verdict) so attribution is one table read.
--
-- selloff_engine_reports: the journaled daily review — cohort stats,
--   fastest rebounders, bounded correction suggestions. Advisory
--   only; decision_weight 0 — weights change by human commit, the
--   engine never rewrites itself.

SELECT pg_advisory_xact_lock(715231);

CREATE TABLE IF NOT EXISTS selloff_grades (
    id              BIGSERIAL PRIMARY KEY,
    as_of           DATE NOT NULL,
    symbol          TEXT NOT NULL,
    anchor_close    NUMERIC(12,4),   -- signal-day close
    sbd_class       TEXT,            -- beat_down_stock / beat_down_business / …
    decision        TEXT,            -- priority / starter / watch / pass / reject
    pf_gap          NUMERIC(8,4),    -- price-fundamental gap at signal
    session_action  TEXT,            -- stability-job verdict that day
    session_sas     NUMERIC(5,1),    -- stock accumulation score
    session_mss     NUMERIC(5,1),    -- market stability score
    ret_5d          NUMERIC(8,2),
    ret_10d         NUMERIC(8,2),
    ret_20d         NUMERIC(8,2),
    rel_ret_10d     NUMERIC(8,2),    -- vs QQQ same window
    rel_ret_20d     NUMERIC(8,2),
    mfe_20d         NUMERIC(8,2),    -- best close gain within 20d
    mae_20d         NUMERIC(8,2),    -- worst close loss within 20d
    days_to_mfe     INT,
    days_to_plus10  INT,             -- first close ≥ +10% off anchor
    days_underwater INT,             -- closes below anchor within 20d
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (as_of, symbol)
);
CREATE INDEX IF NOT EXISTS selloff_grades_asof_idx
    ON selloff_grades (as_of DESC);
CREATE INDEX IF NOT EXISTS selloff_grades_sbd_idx
    ON selloff_grades (sbd_class) WHERE rel_ret_10d IS NOT NULL;

CREATE TABLE IF NOT EXISTS selloff_engine_reports (
    id         BIGSERIAL PRIMARY KEY,
    as_of      DATE NOT NULL UNIQUE,
    n_graded   INT,
    report     JSONB,                -- cohorts + fastest + suggestions
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
