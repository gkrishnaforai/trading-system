-- spec_pulse_evals — the spec sleeve's eval journal (first-write-
-- per-day). Same training-ledger role as pulse_rule_evals: meta can
-- later grade 'did harvest precede tops / thesis_check precede cuts'.

CREATE TABLE IF NOT EXISTS spec_pulse_evals (
    id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    as_of       date NOT NULL,
    symbol      text NOT NULL,
    kind        text NOT NULL,            -- position | watch
    bucket      text NOT NULL,            -- runner/buy_a_lot/.../cut
    tier        text,
    engine      text,
    mom_state   text,
    fund_state  text,
    gates_met   integer,
    rev_growth  double precision,
    evidence    jsonb NOT NULL DEFAULT '{}',
    created_at  timestamptz DEFAULT now(),
    UNIQUE (as_of, symbol)
);

CREATE INDEX IF NOT EXISTS spec_pulse_evals_date_idx
    ON spec_pulse_evals (as_of DESC);
