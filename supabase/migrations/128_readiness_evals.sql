-- 128_readiness_evals.sql — daily journal of the use-case readiness
-- checklists (swing / invest / leap_call / leap_put), board-wide.
-- pulse_rule_evals covers only portfolio+watchlist symbols— this
-- covers the full universe so transitions ("moved to ready",
-- "dropped to blocked") are queryable — and, joined to outcomes
-- later, the training/calibration substrate for the checklists.
-- First write of the day per rules_version wins — same contract as
-- pulse_rule_evals.

CREATE TABLE IF NOT EXISTS readiness_evals (
    id              bigserial PRIMARY KEY,
    symbol          text NOT NULL,
    as_of           date NOT NULL,
    use_case        text NOT NULL,              -- swing|invest|leap_call|leap_put
    state           text NOT NULL,              -- ready|close|no
    score           int,
    of              int,
    fails           jsonb,                      -- blocking checklist lines
    mom             text,
    fund            text,
    rules_version   text NOT NULL,
    engine_version  text NOT NULL,
    created_at      timestamptz DEFAULT now(),
    UNIQUE (symbol, as_of, use_case, rules_version)
);
CREATE INDEX IF NOT EXISTS idx_re_evals_sym
    ON readiness_evals (symbol, use_case, as_of);
CREATE INDEX IF NOT EXISTS idx_re_evals_state
    ON readiness_evals (state, as_of);
