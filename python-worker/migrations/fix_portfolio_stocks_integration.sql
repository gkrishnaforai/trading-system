-- ========================================
-- FIX PORTFOLIO-STOCKS INTEGRATION
-- Add proper foreign key relationships and ensure data integrity
-- ========================================

-- Step 1: Add foreign key constraint from portfolio_holdings to stocks table
-- This ensures only valid stock symbols can be added to portfolios
DO $$
BEGIN
    -- Check if constraint exists before adding
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.table_constraints 
        WHERE constraint_name = 'fk_portfolio_holdings_stock'
        AND table_name = 'portfolio_holdings'
    ) THEN
        ALTER TABLE portfolio_holdings 
        ADD CONSTRAINT fk_portfolio_holdings_stock 
        FOREIGN KEY (symbol) REFERENCES stocks(symbol) 
        ON DELETE RESTRICT;
        
        RAISE NOTICE 'Added foreign key constraint from portfolio_holdings to stocks';
    END IF;
END $$;

-- Step 2: Create a function to sync symbols between symbol_master and stocks
CREATE OR REPLACE FUNCTION sync_symbol_with_stocks()
RETURNS TRIGGER AS $$
BEGIN
    -- When a new stock is added, ensure it exists in symbol_master
    INSERT INTO symbol_master (symbol, asset_type, first_analyzed, last_analyzed)
    VALUES (NEW.symbol, 'stock', CURRENT_DATE, CURRENT_DATE)
    ON CONFLICT (symbol) DO UPDATE SET
        last_analyzed = CURRENT_DATE,
        updated_at = CURRENT_TIMESTAMP;
    
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Step 3: Add trigger to auto-sync new stocks to symbol_master
CREATE TRIGGER sync_stock_to_symbol_master
AFTER INSERT ON stocks
FOR EACH ROW
EXECUTE FUNCTION sync_symbol_with_stocks();

-- Step 4: Create a function to validate portfolio holdings
CREATE OR REPLACE FUNCTION validate_portfolio_holdings()
RETURNS TABLE(portfolio_id INTEGER, symbol VARCHAR(10), issue TEXT) AS $$
BEGIN
    -- Find portfolio holdings with symbols not in stocks table
    RETURN QUERY
    SELECT 
        ph.portfolio_id,
        ph.symbol,
        'Symbol not found in stocks table'
    FROM portfolio_holdings ph
    LEFT JOIN stocks s ON ph.symbol = s.symbol
    WHERE s.symbol IS NULL;
    
    -- Find portfolio holdings with invalid asset types
    RETURN QUERY
    SELECT 
        ph.portfolio_id,
        ph.symbol,
        'Invalid asset type for stock'
    FROM portfolio_holdings ph
    INNER JOIN stocks s ON ph.symbol = s.symbol
    WHERE ph.asset_type NOT IN ('stock', 'regular_etf', '3x_etf')
    AND s.symbol IS NOT NULL;
END;
$$ LANGUAGE plpgsql;

-- Step 5: Create a view for portfolio holdings with stock information
CREATE OR REPLACE VIEW portfolio_holdings_enriched AS
SELECT 
    ph.id,
    ph.portfolio_id,
    ph.symbol,
    ph.asset_type,
    ph.shares_held,
    ph.average_cost,
    ph.status,
    ph.created_at,
    ph.updated_at,
    ph.notes,
    -- Stock information
    s.company_name,
    s.exchange,
    s.sector,
    s.industry,
    s.market_cap,
    s.country,
    s.currency as stock_currency,
    s.is_active as stock_is_active,
    -- Data completeness flags
    s.has_fundamentals,
    s.has_earnings,
    s.has_market_data,
    s.has_indicators
FROM portfolio_holdings ph
INNER JOIN stocks s ON ph.symbol = s.symbol;

-- Step 6: Create indexes for better performance
CREATE INDEX IF NOT EXISTS idx_portfolio_holdings_symbol_fk ON portfolio_holdings(symbol);
CREATE INDEX IF NOT EXISTS idx_portfolio_holdings_enriched_symbol ON portfolio_holdings_enriched(symbol);
CREATE INDEX IF NOT EXISTS idx_portfolio_holdings_enriched_sector ON portfolio_holdings_enriched(sector);

-- Step 7: Add validation function for portfolio operations
CREATE OR REPLACE FUNCTION validate_portfolio_symbol(p_symbol VARCHAR(10))
RETURNS BOOLEAN AS $$
DECLARE
    stock_exists BOOLEAN;
BEGIN
    -- Check if symbol exists in stocks table
    SELECT EXISTS(SELECT 1 FROM stocks WHERE symbol = p_symbol AND is_active = TRUE)
    INTO stock_exists;
    
    IF NOT stock_exists THEN
        RAISE EXCEPTION 'Symbol % does not exist in stocks table or is not active', p_symbol;
    END IF;
    
    RETURN TRUE;
END;
$$ LANGUAGE plpgsql;

-- Step 8: Add trigger to validate symbols before adding to portfolio
CREATE OR REPLACE FUNCTION validate_portfolio_holding_before_insert()
RETURNS TRIGGER AS $$
BEGIN
    PERFORM validate_portfolio_symbol(NEW.symbol);
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER validate_portfolio_holding_insert
BEFORE INSERT ON portfolio_holdings
FOR EACH ROW
EXECUTE FUNCTION validate_portfolio_holding_before_insert();

-- Step 9: Create a procedure to clean up orphaned holdings
CREATE OR REPLACE FUNCTION cleanup_orphaned_holdings()
RETURNS INTEGER AS $$
DECLARE
    cleanup_count INTEGER;
BEGIN
    -- Delete holdings where symbol doesn't exist in stocks table
    DELETE FROM portfolio_holdings
    WHERE symbol NOT IN (SELECT symbol FROM stocks WHERE is_active = TRUE);
    
    GET DIAGNOSTICS cleanup_count = ROW_COUNT;
    
    RAISE NOTICE 'Cleaned up % orphaned portfolio holdings', cleanup_count;
    RETURN cleanup_count;
END;
$$ LANGUAGE plpgsql;

-- Step 10: Create a procedure to sync existing symbols
CREATE OR REPLACE FUNCTION sync_existing_symbols_to_stocks()
RETURNS INTEGER AS $$
DECLARE
    sync_count INTEGER;
BEGIN
    -- Insert symbols from symbol_master that don't exist in stocks
    INSERT INTO stocks (symbol, company_name, sector, industry, asset_type)
    SELECT 
        sm.symbol,
        sm.company_name,
        sm.sector,
        sm.industry,
        CASE 
            WHEN sm.asset_type IN ('stock', 'regular_etf', '3x_etf') THEN sm.asset_type
            ELSE 'stock'
        END
    FROM symbol_master sm
    LEFT JOIN stocks s ON sm.symbol = s.symbol
    WHERE s.symbol IS NULL;
    
    GET DIAGNOSTICS sync_count = ROW_COUNT;
    
    RAISE NOTICE 'Synced % symbols from symbol_master to stocks', sync_count;
    RETURN sync_count;
END;
$$ LANGUAGE plpgsql;

-- Run initial sync
SELECT sync_existing_symbols_to_stocks() as symbols_synced;

-- Create a summary view for portfolio health
CREATE OR REPLACE VIEW portfolio_health_summary AS
SELECT 
    p.id as portfolio_id,
    p.name as portfolio_name,
    COUNT(ph.id) as total_holdings,
    COUNT(CASE WHEN s.symbol IS NULL THEN 1 END) as orphaned_holdings,
    COUNT(CASE WHEN s.is_active = FALSE THEN 1 END) as inactive_stock_holdings,
    COUNT(CASE WHEN s.has_fundamentals = FALSE THEN 1 END) as holdings_missing_fundamentals,
    COUNT(CASE WHEN s.has_market_data = FALSE THEN 1 END) as holdings_missing_market_data,
    SUM(ph.shares_held * ph.average_cost) as total_cost,
    p.created_at
FROM portfolios p
LEFT JOIN portfolio_holdings ph ON p.id = ph.portfolio_id
LEFT JOIN stocks s ON ph.symbol = s.symbol
GROUP BY p.id, p.name, p.created_at;

COMMENT ON TABLE portfolio_health_summary IS 'Summary view showing portfolio health and data completeness';
COMMENT ON VIEW portfolio_holdings_enriched IS 'Portfolio holdings enriched with stock information';
COMMENT ON FUNCTION validate_portfolio_holdings() IS 'Validates portfolio holdings for data integrity issues';
COMMENT ON FUNCTION cleanup_orphaned_holdings() IS 'Removes portfolio holdings with invalid stock symbols';
COMMENT ON FUNCTION sync_existing_symbols_to_stocks() IS 'Syncs symbols from symbol_master to stocks table';
