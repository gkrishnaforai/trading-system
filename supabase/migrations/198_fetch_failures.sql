-- 198_fetch_failures.sql — provider-level failure ledger. Terminal
-- fetch failures (after retries exhausted) land here via
-- http_resilience.fail() — the custodian reads it to distinguish a
-- transient blip from a provider outage, and it gives the circuit
-- breaker history beyond in-memory state.
SELECT pg_advisory_xact_lock(715198);

CREATE TABLE IF NOT EXISTS fetch_failures (
    id          bigserial PRIMARY KEY,
    provider    TEXT NOT NULL,
    endpoint    TEXT NOT NULL,
    error       TEXT NOT NULL,
    latency_ms  INT,
    occurred_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_ff_provider_time
    ON fetch_failures (provider, occurred_at DESC);
