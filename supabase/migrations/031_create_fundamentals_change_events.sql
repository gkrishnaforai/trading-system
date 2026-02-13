CREATE TABLE IF NOT EXISTS fundamentals_change_events (
    id BIGSERIAL PRIMARY KEY,
    stock_symbol TEXT NOT NULL,
    as_of_date DATE NOT NULL,
    event_type TEXT NOT NULL,
    event_key TEXT NOT NULL,
    headline TEXT NOT NULL,
    severity TEXT NOT NULL,
    direction TEXT NOT NULL,
    evidence JSONB,
    recommended_action TEXT,
    payload JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_fundamentals_change_events_symbol_asof_type_key
ON fundamentals_change_events(stock_symbol, as_of_date, event_type, event_key);

CREATE INDEX IF NOT EXISTS idx_fundamentals_change_events_symbol_created
ON fundamentals_change_events(stock_symbol, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_fundamentals_change_events_symbol_asof
ON fundamentals_change_events(stock_symbol, as_of_date DESC);
