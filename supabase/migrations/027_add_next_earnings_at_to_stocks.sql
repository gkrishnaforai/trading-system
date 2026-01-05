ALTER TABLE IF EXISTS stocks
  ADD COLUMN IF NOT EXISTS next_earnings_at TIMESTAMPTZ,
  ADD COLUMN IF NOT EXISTS next_earnings_timezone TEXT;

CREATE INDEX IF NOT EXISTS idx_stocks_next_earnings_at
ON stocks(next_earnings_at);
