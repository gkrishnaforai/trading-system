-- Add volume fields to aggregated_indicators table
-- Volume data is needed for volume analysis in Stock Analysis page

ALTER TABLE aggregated_indicators ADD COLUMN volume INTEGER;
ALTER TABLE aggregated_indicators ADD COLUMN volume_ma REAL; -- Volume moving average (20-day)

-- Create index for volume queries
CREATE INDEX IF NOT EXISTS idx_aggregated_indicators_volume ON aggregated_indicators(stock_symbol, date DESC, volume);

