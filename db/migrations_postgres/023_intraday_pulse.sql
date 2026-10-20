-- 023: intraday tape evals
-- 15-min journaled tape states during RTH. The learning loop grades
-- "did state X at time T hold to the close" — states earn trust from
-- outcomes, not plausibility.

CREATE TABLE IF NOT EXISTS intraday_evals (
    id          BIGSERIAL PRIMARY KEY,
    ts          TIMESTAMPTZ NOT NULL,
    state       TEXT NOT NULL,
    readings    JSONB,
    outcome     TEXT,                 -- hit | miss (graded next day)
    day_ret     NUMERIC(8,4),
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_ie_ts ON intraday_evals (ts DESC);
CREATE INDEX IF NOT EXISTS idx_ie_state ON intraday_evals (state, ts DESC);
