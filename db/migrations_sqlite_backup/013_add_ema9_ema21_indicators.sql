-- Migration 013: Add ema9 and ema21 columns to aggregated_indicators for swing trading
-- These indicators are required for swing trading strategies

ALTER TABLE aggregated_indicators ADD COLUMN ema9 REAL;
ALTER TABLE aggregated_indicators ADD COLUMN ema21 REAL;

CREATE INDEX IF NOT EXISTS idx_indicators_ema9 ON aggregated_indicators(stock_symbol, date) WHERE ema9 IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_indicators_ema21 ON aggregated_indicators(stock_symbol, date) WHERE ema21 IS NOT NULL;

