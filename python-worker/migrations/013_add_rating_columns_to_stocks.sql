-- ========================================
-- ADD RATING COLUMNS TO STOCKS TABLE
-- Migration: 013_add_rating_columns_to_stocks.sql
-- Add rating and price target columns to stocks table
-- ========================================

-- Add rating-related columns to stocks table
ALTER TABLE stocks 
ADD COLUMN IF NOT EXISTS rating VARCHAR(20),
ADD COLUMN IF NOT EXISTS price_target DECIMAL(10,2),
ADD COLUMN IF NOT EXISTS rating_score DECIMAL(4,2),
ADD COLUMN IF NOT EXISTS rating_updated_at TIMESTAMPTZ,
ADD COLUMN IF NOT EXISTS rating_data_source VARCHAR(50) DEFAULT 'fmp';

-- Add indexes for performance
CREATE INDEX IF NOT EXISTS idx_stocks_rating ON stocks(rating);
CREATE INDEX IF NOT EXISTS idx_stocks_rating_updated ON stocks(rating_updated_at);
CREATE INDEX IF NOT EXISTS idx_stocks_price_target ON stocks(price_target);

-- Create rating change log table
CREATE TABLE IF NOT EXISTS rating_change_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    symbol VARCHAR(10) NOT NULL REFERENCES stocks(symbol) ON DELETE CASCADE,
    old_rating VARCHAR(20),
    new_rating VARCHAR(20),
    old_price_target DECIMAL(10,2),
    new_price_target DECIMAL(10,2),
    consensus_score DECIMAL(4,2),
    change_type VARCHAR(50), -- 'rating', 'price_target', 'both'
    data_source VARCHAR(50) DEFAULT 'fmp',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes for rating change log
CREATE INDEX IF NOT EXISTS idx_rating_change_log_symbol ON rating_change_log(symbol);
CREATE INDEX IF NOT EXISTS idx_rating_change_log_created ON rating_change_log(created_at);
CREATE INDEX IF NOT EXISTS idx_rating_change_log_type ON rating_change_log(change_type);

-- Add comments
COMMENT ON COLUMN stocks.rating IS 'Current consensus analyst rating (Buy, Sell, Hold, etc.)';
COMMENT ON COLUMN stocks.price_target IS 'Consensus price target from analysts';
COMMENT ON COLUMN stocks.rating_score IS 'Numeric consensus score (-2 to +2 scale)';
COMMENT ON COLUMN stocks.rating_updated_at IS 'Last time rating data was updated';
COMMENT ON COLUMN stocks.rating_data_source IS 'Source of rating data (fmp, bloomberg, etc.)';

COMMENT ON TABLE rating_change_log IS 'Audit trail of rating and price target changes';
