-- insider_transactions — raw Form-4-style insider flow, append-only.
-- The audit trail behind event_type='insider' alerts: every filing
-- that fed a cluster verdict is replayable. Code P (open-market
-- purchase) and S (sale) are the signal; grants/options/awards are
-- stored for completeness but never drive alerts.
CREATE TABLE IF NOT EXISTS insider_transactions (
    id               BIGSERIAL PRIMARY KEY,
    symbol           TEXT NOT NULL,
    insider_name     TEXT,
    transaction_code TEXT,             -- P buy | S sell | A grant | etc
    shares           DOUBLE PRECISION,
    change           DOUBLE PRECISION, -- share delta reported
    price            DOUBLE PRECISION,
    transaction_date DATE,
    filing_date      DATE,
    source           TEXT NOT NULL DEFAULT 'finnhub',
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (symbol, insider_name, transaction_code, shares,
            transaction_date, filing_date)
);

CREATE INDEX IF NOT EXISTS idx_insider_tx_symbol_date
    ON insider_transactions (symbol, transaction_date DESC);
CREATE INDEX IF NOT EXISTS idx_insider_tx_code_date
    ON insider_transactions (transaction_code, transaction_date DESC);

-- daily 06:30 UTC — pre-open, after the nightly fundamental jobs so
-- today's alert gate sees fresh insider clusters
INSERT INTO job_definitions (name, label, cron, enabled)
VALUES ('insider-flow', 'Insider buy/sell flow', '30 6 * * *', true)
ON CONFLICT (name) DO NOTHING;
