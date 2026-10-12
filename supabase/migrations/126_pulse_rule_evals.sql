-- 126_pulse_rule_evals.sql — deterministic action-engine journal.
-- One row per symbol per day per rules version: which rule matched,
-- every condition's pass/fail/missing, annotations, gate outcomes,
-- and the input snapshot. This is the audit + learning substrate —
-- outcomes join later on as_of + horizon— rule changes are judged
-- against journaled evals, never on narrative.

CREATE TABLE IF NOT EXISTS pulse_rule_evals (
    id              bigserial PRIMARY KEY,
    symbol          text NOT NULL,
    as_of           date NOT NULL,
    kind            text,                       -- position | watch
    action          text NOT NULL,              -- reduce|trim|watch|add|hold
    label           text,
    matched_rule    text,
    confidence      text,
    stage0          jsonb,      -- computed inputs: fv_valid, rev_class,
                                -- instrument, tape_dir
    annotations     jsonb,      -- blocking, confidence, risk flags
    condition_log   jsonb,      -- ordered per-rule cond results
    gate_results    jsonb,      -- add_policy per-gate pass/fail
    input_snapshot  jsonb,      -- raw inputs as evaluated
    rules_version   text NOT NULL,
    engine_version  text NOT NULL,
    created_at      timestamptz DEFAULT now(),
    UNIQUE (symbol, as_of, rules_version)
);
CREATE INDEX IF NOT EXISTS idx_pre_action
    ON pulse_rule_evals (action, as_of);
CREATE INDEX IF NOT EXISTS idx_pre_symbol
    ON pulse_rule_evals (symbol, as_of);
