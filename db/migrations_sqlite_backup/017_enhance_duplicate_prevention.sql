-- Enhance duplicate prevention for different data frequencies
-- Industry Standard: Idempotent operations, no duplicate data

-- Add indexes for faster duplicate checks
CREATE INDEX IF NOT EXISTS idx_raw_market_symbol_date ON raw_market_data(stock_symbol, date DESC);
CREATE INDEX IF NOT EXISTS idx_indicators_symbol_date ON aggregated_indicators(stock_symbol, date DESC);
CREATE INDEX IF NOT EXISTS idx_earnings_symbol_date ON earnings_data(stock_symbol, earnings_date DESC);
CREATE INDEX IF NOT EXISTS idx_news_symbol_date ON stock_news(stock_symbol, published_date DESC);

-- Add timestamp tracking for data freshness
-- This helps identify stale data and prevent overwriting fresh data with old data
-- SQLite doesn't support DEFAULT CURRENT_TIMESTAMP in ALTER TABLE, so we add without default
-- Application code will set updated_at on insert/update
ALTER TABLE raw_market_data ADD COLUMN updated_at TIMESTAMP;
ALTER TABLE aggregated_indicators ADD COLUMN updated_at TIMESTAMP;

-- Update existing rows to set updated_at to current timestamp
-- SQLite: Use datetime('now') for current timestamp
UPDATE raw_market_data SET updated_at = datetime('now') WHERE updated_at IS NULL;
UPDATE aggregated_indicators SET updated_at = datetime('now') WHERE updated_at IS NULL;

-- Create trigger to update updated_at on row update
-- SQLite doesn't support triggers with OR REPLACE, so we'll handle this in application code
-- But we can add a check constraint for data freshness

-- Add data_source tracking to prevent conflicts from multiple sources
-- SQLite doesn't support DEFAULT in ALTER TABLE, so we add without default
-- Application code will set default values on insert
ALTER TABLE raw_market_data ADD COLUMN data_source TEXT;
ALTER TABLE raw_market_data ADD COLUMN data_frequency TEXT CHECK(data_frequency IN ('intraday', 'daily', 'weekly', 'monthly', 'quarterly', 'yearly'));

-- Update existing rows to set default values
UPDATE raw_market_data SET data_source = 'yahoo_finance' WHERE data_source IS NULL;
UPDATE raw_market_data SET data_frequency = 'daily' WHERE data_frequency IS NULL;

-- Add data_source and data_frequency to aggregated_indicators as well
ALTER TABLE aggregated_indicators ADD COLUMN data_source TEXT;
ALTER TABLE aggregated_indicators ADD COLUMN data_frequency TEXT CHECK(data_frequency IN ('intraday', 'daily', 'weekly', 'monthly', 'quarterly', 'yearly'));

-- Update existing rows in aggregated_indicators
UPDATE aggregated_indicators SET data_source = 'yahoo_finance' WHERE data_source IS NULL;
UPDATE aggregated_indicators SET data_frequency = 'daily' WHERE data_frequency IS NULL;

-- Create view for latest data per symbol (helps with duplicate detection)
CREATE VIEW IF NOT EXISTS latest_market_data AS
SELECT 
    stock_symbol,
    MAX(date) as latest_date,
    COUNT(*) as total_records,
    MIN(date) as earliest_date
FROM raw_market_data
GROUP BY stock_symbol;

-- Create view for duplicate detection
CREATE VIEW IF NOT EXISTS potential_duplicates AS
SELECT 
    stock_symbol,
    date,
    COUNT(*) as duplicate_count,
    GROUP_CONCAT(id) as record_ids
FROM raw_market_data
GROUP BY stock_symbol, date
HAVING COUNT(*) > 1;

-- Note: The UNIQUE constraint on (stock_symbol, date) should prevent duplicates
-- But this view helps identify any that might exist from before the constraint was added

