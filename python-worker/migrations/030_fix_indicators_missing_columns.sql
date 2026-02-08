-- Fix indicators_daily table - add missing indicator_value column
-- The table was converted to wide format but we need narrow format support

DO
$$
BEGIN
    -- Add the missing indicator_value column if it doesn't exist
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'indicators_daily' AND column_name = 'indicator_value') THEN
        ALTER TABLE indicators_daily ADD COLUMN indicator_value NUMERIC(12, 6);
    END IF;
    
    -- Add the missing id column if it doesn't exist (for primary key)
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'indicators_daily' AND column_name = 'id') THEN
        ALTER TABLE indicators_daily ADD COLUMN id SERIAL PRIMARY KEY;
    END IF;
    
    -- Add the missing time_period column if it doesn't exist
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'indicators_daily' AND column_name = 'time_period') THEN
        ALTER TABLE indicators_daily ADD COLUMN time_period INTEGER;
    END IF;
    
END
$$;

-- Create index for indicator_value for better query performance
CREATE INDEX IF NOT EXISTS idx_indicators_daily_value ON indicators_daily(indicator_value);

-- Add comment
COMMENT ON COLUMN indicators_daily.indicator_value IS 'Value of the indicator (for narrow format storage)';
COMMENT ON COLUMN indicators_daily.time_period IS 'Time period for the indicator (e.g., 14 for RSI-14)';

-- Verify the table structure
SELECT column_name, data_type, is_nullable 
FROM information_schema.columns 
WHERE table_name = 'indicators_daily' 
ORDER BY column_name;
