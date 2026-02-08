-- Add wide indicators columns and proper constraint for indicators_daily
-- This migration supports the new indicator service that stores all indicators in one row

DO
$$
BEGIN
    -- Add wide indicator columns if they don't exist
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'indicators_daily' AND column_name = 'sma_50') THEN
        ALTER TABLE indicators_daily ADD COLUMN sma_50 NUMERIC(12, 6);
    END IF;
    
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'indicators_daily' AND column_name = 'sma_200') THEN
        ALTER TABLE indicators_daily ADD COLUMN sma_200 NUMERIC(12, 6);
    END IF;
    
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'indicators_daily' AND column_name = 'ema_20') THEN
        ALTER TABLE indicators_daily ADD COLUMN ema_20 NUMERIC(12, 6);
    END IF;
    
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'indicators_daily' AND column_name = 'rsi_14') THEN
        ALTER TABLE indicators_daily ADD COLUMN rsi_14 NUMERIC(12, 6);
    END IF;
    
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'indicators_daily' AND column_name = 'macd') THEN
        ALTER TABLE indicators_daily ADD COLUMN macd NUMERIC(12, 6);
    END IF;
    
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'indicators_daily' AND column_name = 'macd_signal') THEN
        ALTER TABLE indicators_daily ADD COLUMN macd_signal NUMERIC(12, 6);
    END IF;
    
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'indicators_daily' AND column_name = 'macd_hist') THEN
        ALTER TABLE indicators_daily ADD COLUMN macd_hist NUMERIC(12, 6);
    END IF;
    
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'indicators_daily' AND column_name = 'atr') THEN
        ALTER TABLE indicators_daily ADD COLUMN atr NUMERIC(12, 6);
    END IF;
    
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'indicators_daily' AND column_name = 'bb_width') THEN
        ALTER TABLE indicators_daily ADD COLUMN bb_width NUMERIC(12, 6);
    END IF;
    
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'indicators_daily' AND column_name = 'signal') THEN
        ALTER TABLE indicators_daily ADD COLUMN signal VARCHAR(20);
    END IF;
    
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'indicators_daily' AND column_name = 'confidence_score') THEN
        ALTER TABLE indicators_daily ADD COLUMN confidence_score NUMERIC(3, 2);
    END IF;
    
    -- Drop the old constraint if it exists
    IF EXISTS (SELECT 1 FROM information_schema.table_constraints 
               WHERE table_name = 'indicators_daily' 
               AND constraint_name = 'indicators_daily_symbol_date_indicator_name_data_source_key') THEN
        ALTER TABLE indicators_daily DROP CONSTRAINT indicators_daily_symbol_date_indicator_name_data_source_key;
    END IF;
    
    -- Add the new constraint for wide row format
    IF NOT EXISTS (SELECT 1 FROM information_schema.table_constraints 
                   WHERE table_name = 'indicators_daily' 
                   AND constraint_name = 'indicators_daily_symbol_date_unique') THEN
        ALTER TABLE indicators_daily ADD CONSTRAINT indicators_daily_symbol_date_unique UNIQUE (symbol, date);
    END IF;
    
    -- Add updated_at column if it doesn't exist
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'indicators_daily' AND column_name = 'updated_at') THEN
        ALTER TABLE indicators_daily ADD COLUMN updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP;
    END IF;
    
END
$$;

-- Create index for the new constraint
CREATE INDEX IF NOT EXISTS idx_indicators_daily_symbol_date ON indicators_daily(symbol, date);

-- Add comments
COMMENT ON COLUMN indicators_daily.sma_50 IS '50-day Simple Moving Average';
COMMENT ON COLUMN indicators_daily.sma_200 IS '200-day Simple Moving Average';
COMMENT ON COLUMN indicators_daily.ema_20 IS '20-day Exponential Moving Average';
COMMENT ON COLUMN indicators_daily.rsi_14 IS '14-day Relative Strength Index';
COMMENT ON COLUMN indicators_daily.macd IS 'MACD Line';
COMMENT ON COLUMN indicators_daily.macd_signal IS 'MACD Signal Line';
COMMENT ON COLUMN indicators_daily.macd_hist IS 'MACD Histogram';
COMMENT ON COLUMN indicators_daily.atr IS 'Average True Range';
COMMENT ON COLUMN indicators_daily.bb_width IS 'Bollinger Band Width';
COMMENT ON COLUMN indicators_daily.signal IS 'Trading Signal (buy/sell/hold)';
COMMENT ON COLUMN indicators_daily.confidence_score IS 'Signal Confidence Score (0-1)';
COMMENT ON COLUMN indicators_daily.updated_at IS 'Last update timestamp';
