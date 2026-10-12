-- Regime snapshots — version the board's daily regime read so it can
-- be graded: forward probabilities, dip character, allocation stance.
-- One row/day; the evaluator fills realized SPY returns at 20/60d and
-- whether the lead scenario matched reality.
CREATE TABLE IF NOT EXISTS regime_snapshots (
    id            bigserial PRIMARY KEY,
    as_of         date NOT NULL UNIQUE,
    stance        text,
    vix           double precision,
    spy_vs_200    double precision,
    p_deeper      int,
    p_chop        int,
    p_bull        int,
    lead_scenario text,                    -- dip | chop | growth
    dip_character text,                    -- deleveraging | rotation …
    ai_rs20       double precision,
    cash_buffer   int,
    payload       jsonb,                   -- full posture dict
    spy_ret_20d   double precision,        -- graded: realized SPY
    spy_ret_60d   double precision,
    lead_correct  boolean,                 -- did lead scenario win?
    graded_at     timestamptz,
    created_at    timestamptz DEFAULT now()
);
CREATE INDEX IF NOT EXISTS regime_snap_date_idx
    ON regime_snapshots (as_of DESC);
