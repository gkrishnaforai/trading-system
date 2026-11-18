-- recovery_verdicts — the Phase-1 composition journal. One row per
-- symbol/day/engine_version: state machine position, advisory
-- decision, gates, conflicts, evidence refs, and what inputs were
-- missing. state_changed + transition_reason make selloff sequences
-- (COHR Nov 5-17) replayable from the journal alone.
CREATE TABLE IF NOT EXISTS recovery_verdicts (
    id                     BIGSERIAL PRIMARY KEY,
    symbol                 TEXT NOT NULL,
    as_of                  DATE NOT NULL,
    engine_version         TEXT NOT NULL,
    state                  TEXT NOT NULL,
    prev_state             TEXT,
    state_changed          BOOLEAN NOT NULL DEFAULT false,
    transition_reason      TEXT,
    event_type             TEXT,
    market                 JSONB,
    stock                  JSONB,
    recovery               JSONB,
    decision               TEXT,          -- advisory only in Phase 1
    decision_confidence    TEXT,          -- low|provisional|normal
    gates                  JSONB,
    conflicts              JSONB,
    required_confirmation  JSONB,
    invalidation_conditions JSONB,
    evidence_refs          JSONB,
    missing_inputs         JSONB,
    detail                 JSONB,
    created_at             TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (symbol, as_of, engine_version)
);

CREATE INDEX IF NOT EXISTS idx_recovery_verdicts_sym_date
    ON recovery_verdicts (symbol, as_of DESC);
CREATE INDEX IF NOT EXISTS idx_recovery_verdicts_state
    ON recovery_verdicts (state, as_of DESC);

-- daily 06:45 UTC — after morning-regime + selloff journals land
INSERT INTO job_definitions (name, label, cron, enabled)
VALUES ('recovery-watch', 'Recovery verdicts (pilot)', '45 6 * * *', true)
ON CONFLICT (name) DO NOTHING;
