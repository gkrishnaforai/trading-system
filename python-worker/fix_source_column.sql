-- Add source column to raw_market_data_intraday if it doesn't exist
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'raw_market_data_intraday' 
        AND column_name = 'source'
    ) THEN
        ALTER TABLE raw_market_data_intraday ADD COLUMN source TEXT;
        
        -- Update primary key to include source
        ALTER TABLE raw_market_data_intraday DROP CONSTRAINT raw_market_data_intraday_pkey;
        ALTER TABLE raw_market_data_intraday ADD PRIMARY KEY (stock_symbol, ts, interval, source);
        
        RAISE NOTICE 'Added source column to raw_market_data_intraday';
    ELSE
        RAISE NOTICE 'Source column already exists in raw_market_data_intraday';
    END IF;
END $$;
