-- crypto_positioning_daily — the positioning layer behind crypto's
-- x-asset vote: stablecoin supply, futures OI, ETF flows, trend/
-- leadership — banded votes journaled daily for forward grading.
CREATE TABLE IF NOT EXISTS crypto_positioning_daily (
    id         BIGSERIAL PRIMARY KEY,
    as_of      DATE NOT NULL UNIQUE,
    stance     TEXT,                -- accumulation|neutral|distribution
    legs       JSONB,               -- per-signal votes + raw values
    payload    JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- daily 06:50 UTC — after bars + before the morning read
INSERT INTO job_definitions (name, label, cron, enabled)
VALUES ('crypto-positioning', 'Crypto positioning signals', '50 6 * * *', true)
ON CONFLICT (name) DO NOTHING;
