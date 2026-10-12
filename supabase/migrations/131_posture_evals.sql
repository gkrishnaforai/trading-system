-- Posture journal + outcome grading. Evals journal each day's
-- trade posture (first write per day per rules_version wins);
-- outcomes grade each eval against forward QQQ returns — the
-- journal IS the backtest.
CREATE TABLE IF NOT EXISTS posture_evals (
    id            bigserial PRIMARY KEY,
    as_of         date        NOT NULL,
    posture       text        NOT NULL,
    new_longs     boolean     NOT NULL,
    shorts        boolean     NOT NULL,
    hedge_on      boolean     NOT NULL,
    matched_rule  text,
    note          text,
    evidence      jsonb,
    rules_version text        NOT NULL,
    created_at    timestamptz NOT NULL DEFAULT now(),
    UNIQUE (as_of, rules_version)
);

CREATE TABLE IF NOT EXISTS posture_outcomes (
    eval_id   bigint PRIMARY KEY REFERENCES posture_evals(id),
    as_of     date NOT NULL,
    posture   text NOT NULL,
    fwd_1d    numeric,
    fwd_5d    numeric,
    fwd_10d   numeric,
    fwd_20d   numeric,
    graded_at timestamptz          -- set when fwd_20d is filled
);
CREATE INDEX IF NOT EXISTS posture_outcomes_posture_idx
    ON posture_outcomes (posture);
