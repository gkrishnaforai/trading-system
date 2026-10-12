-- Symbol-level momentum regime flag — canonical daily state, written
-- once by momentum_regime.refresh_* and read by every surface
-- (Options scan, Market Movers boards, 5x Scout, LEAPS book).
-- Pattern mirrors stocks.cyclical: state + evidence jsonb + timestamp.

ALTER TABLE stocks
    ADD COLUMN IF NOT EXISTS momentum_state TEXT,
    ADD COLUMN IF NOT EXISTS momentum_detail JSONB DEFAULT '{}'::jsonb,
    ADD COLUMN IF NOT EXISTS momentum_updated_at TIMESTAMPTZ;

CREATE INDEX IF NOT EXISTS idx_stocks_momentum_state
    ON stocks (momentum_state);
