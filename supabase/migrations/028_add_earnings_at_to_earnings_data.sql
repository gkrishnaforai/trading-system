ALTER TABLE IF EXISTS earnings_data
  ADD COLUMN IF NOT EXISTS earnings_at TIMESTAMPTZ,
  ADD COLUMN IF NOT EXISTS earnings_timezone TEXT,
  ADD COLUMN IF NOT EXISTS earnings_session TEXT;

UPDATE earnings_data
SET earnings_timezone = 'America/New_York'
WHERE earnings_timezone IS NULL;

UPDATE earnings_data
SET earnings_at = (earnings_date::timestamp AT TIME ZONE COALESCE(earnings_timezone, 'America/New_York'))
WHERE earnings_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_earnings_data_symbol_at
ON earnings_data(stock_symbol, earnings_at DESC);

CREATE INDEX IF NOT EXISTS idx_earnings_data_at
ON earnings_data(earnings_at DESC);
