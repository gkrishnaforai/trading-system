ALTER TABLE IF EXISTS stocks
  ADD COLUMN IF NOT EXISTS next_earnings_date DATE,
  ADD COLUMN IF NOT EXISTS next_earnings_time TEXT,
  ADD COLUMN IF NOT EXISTS next_earnings_session TEXT,
  ADD COLUMN IF NOT EXISTS next_earnings_source TEXT,
  ADD COLUMN IF NOT EXISTS next_earnings_earnings_id TEXT,
  ADD COLUMN IF NOT EXISTS next_earnings_updated_at TIMESTAMPTZ;

CREATE INDEX IF NOT EXISTS idx_stocks_next_earnings_date
ON stocks(next_earnings_date);
