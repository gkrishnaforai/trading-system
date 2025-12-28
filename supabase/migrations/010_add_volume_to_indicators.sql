-- Add volume and volume_ma to aggregated_indicators table
-- PostgreSQL/Supabase compatible

ALTER TABLE aggregated_indicators ADD COLUMN IF NOT EXISTS volume BIGINT;
ALTER TABLE aggregated_indicators ADD COLUMN IF NOT EXISTS volume_ma DOUBLE PRECISION;

-- Add index for faster queries on volume
CREATE INDEX IF NOT EXISTS idx_aggregated_indicators_volume ON aggregated_indicators (stock_symbol, date, volume);

