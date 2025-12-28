-- Add screener flags to aggregated_indicators for fast filtering
-- These flags are calculated daily and stored for efficient screening

ALTER TABLE aggregated_indicators ADD COLUMN IF NOT EXISTS price_below_sma50 BOOLEAN DEFAULT FALSE;
ALTER TABLE aggregated_indicators ADD COLUMN IF NOT EXISTS price_below_sma200 BOOLEAN DEFAULT FALSE;
ALTER TABLE aggregated_indicators ADD COLUMN IF NOT EXISTS has_good_fundamentals BOOLEAN DEFAULT FALSE;
ALTER TABLE aggregated_indicators ADD COLUMN IF NOT EXISTS is_growth_stock BOOLEAN DEFAULT FALSE;
ALTER TABLE aggregated_indicators ADD COLUMN IF NOT EXISTS is_exponential_growth BOOLEAN DEFAULT FALSE;
ALTER TABLE aggregated_indicators ADD COLUMN IF NOT EXISTS fundamental_score REAL; -- 0-100 score

-- Create indexes for fast screening queries
CREATE INDEX IF NOT EXISTS idx_screener_below_sma50 ON aggregated_indicators(price_below_sma50, date DESC);
CREATE INDEX IF NOT EXISTS idx_screener_below_sma200 ON aggregated_indicators(price_below_sma200, date DESC);
CREATE INDEX IF NOT EXISTS idx_screener_good_fundamentals ON aggregated_indicators(has_good_fundamentals, date DESC);
CREATE INDEX IF NOT EXISTS idx_screener_growth ON aggregated_indicators(is_growth_stock, date DESC);
CREATE INDEX IF NOT EXISTS idx_screener_exponential_growth ON aggregated_indicators(is_exponential_growth, date DESC);
CREATE INDEX IF NOT EXISTS idx_screener_fundamental_score ON aggregated_indicators(fundamental_score DESC, date DESC);

-- Create composite index for common screener queries
CREATE INDEX IF NOT EXISTS idx_screener_composite ON aggregated_indicators(
    has_good_fundamentals, 
    price_below_sma50, 
    price_below_sma200,
    is_growth_stock,
    date DESC
);

