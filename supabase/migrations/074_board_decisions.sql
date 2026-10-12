-- 074: Daily Board decision journal — every pick the board publishes gets
-- snapshotted (action, instrument, score, evidence) and graded at fixed
-- forward horizons. This is the accountability loop: which action types,
-- momentum states, and signal combos actually paid.

CREATE TABLE IF NOT EXISTS board_decisions (
    id              BIGSERIAL PRIMARY KEY,
    as_of           DATE NOT NULL,
    symbol          VARCHAR(10) NOT NULL,
    action          VARCHAR(12) NOT NULL,      -- EXIT/TRIM/ACCUMULATE/BOUNCE/PUT
    instrument      VARCHAR(40),
    score           NUMERIC,
    momentum_state  VARCHAR(20),
    posture         VARCHAR(20),               -- FEAR-DEPLOY/GREED-HARVEST/...
    price           NUMERIC,                   -- spot at decision time
    entry           NUMERIC,                   -- from the swing plan if present
    stop            NUMERIC,
    target          NUMERIC,
    evidence        JSONB,                     -- the why[] chain
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (as_of, symbol, action)
);

CREATE TABLE IF NOT EXISTS board_outcomes (
    decision_id     BIGINT NOT NULL REFERENCES board_decisions(id),
    horizon_days    INT NOT NULL,              -- 5/10/20 trading days
    ret_pct         NUMERIC,                   -- fwd return from decision price
    mfe_pct         NUMERIC,                   -- max favorable excursion
    mae_pct         NUMERIC,                   -- max adverse excursion
    PRIMARY KEY (decision_id, horizon_days)
);

CREATE INDEX IF NOT EXISTS board_decisions_as_of ON board_decisions(as_of);
CREATE INDEX IF NOT EXISTS board_decisions_symbol ON board_decisions(symbol);
