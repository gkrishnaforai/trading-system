-- Wheel tracker — manually logged cash-secured puts and covered calls.
-- The daily check reads the latest screen-run price per symbol (no extra
-- provider calls) and flags positions that are threatened or ITM.

CREATE TABLE IF NOT EXISTS wheel_positions (
    id          bigserial PRIMARY KEY,
    symbol      text NOT NULL,
    kind        text NOT NULL CHECK (kind IN ('csp', 'cc')),
    strike      numeric NOT NULL,
    expiry      date NOT NULL,
    contracts   int NOT NULL DEFAULT 1,
    premium     numeric,                  -- per share
    status      text NOT NULL DEFAULT 'open'
                CHECK (status IN ('open', 'assigned', 'called', 'closed', 'expired')),
    notes       text,
    opened_at   timestamptz DEFAULT now(),
    closed_at   timestamptz,
    updated_at  timestamptz DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_wheel_open
    ON wheel_positions (symbol) WHERE status = 'open';
