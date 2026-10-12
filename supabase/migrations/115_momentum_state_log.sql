-- Migration 115: daily journal of momentum_state per symbol
-- written by momentum_regime.write_state on every refresh
-- enables state-transition detection (uptrend -> rolling_over etc)
CREATE TABLE IF NOT EXISTS momentum_state_log (
    id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    symbol      TEXT NOT NULL,
    as_of       DATE NOT NULL DEFAULT CURRENT_DATE,
    state       TEXT NOT NULL,
    detail      JSONB DEFAULT '{}',
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (symbol, as_of)
);
CREATE INDEX IF NOT EXISTS idx_mom_state_log_sym ON momentum_state_log(symbol, as_of DESC);
CREATE INDEX IF NOT EXISTS idx_mom_state_log_date ON momentum_state_log(as_of);
