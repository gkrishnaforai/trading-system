-- Fix financial_statements table schema
-- Run this directly in your PostgreSQL database

-- 1. Check current table structure
\d financial_statements

-- 2. Add missing columns if they don't exist
ALTER TABLE financial_statements 
ADD COLUMN IF NOT EXISTS payload TEXT;

ALTER TABLE financial_statements 
ADD COLUMN IF NOT EXISTS data_source VARCHAR(50);

ALTER TABLE financial_statements 
ADD COLUMN IF NOT EXISTS created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP;

ALTER TABLE financial_statements 
ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP;

-- 3. Add primary key constraint if it doesn't exist
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint 
        WHERE conrelid = 'financial_statements'::regclass 
        AND contype = 'p'
    ) THEN
        ALTER TABLE financial_statements 
        ADD CONSTRAINT financial_statements_pkey 
        PRIMARY KEY (stock_symbol, period_type, statement_type, fiscal_period);
    END IF;
END
$$;

-- 4. Verify the table structure after fixes
\d financial_statements

-- 5. Test insert with the exact same data as the application
BEGIN;
INSERT INTO financial_statements 
(stock_symbol, period_type, statement_type, fiscal_period, payload, data_source, created_at, updated_at)
VALUES (
    'AAPL', 
    'annual', 
    'income_statement', 
    '2026-12-31',
    '{"date": "2021-09-25", "symbol": "AAPL", "reportedCurrency": "USD"}',
    'unknown',
    '2026-01-21 05:57:03',
    '2026-01-21 05:57:03'
)
ON CONFLICT (stock_symbol, period_type, statement_type, fiscal_period)
DO UPDATE SET
    payload = EXCLUDED.payload,
    data_source = EXCLUDED.data_source,
    updated_at = NOW();

-- Verify it was inserted
SELECT stock_symbol, period_type, statement_type, fiscal_period, data_source, 
       LEFT(payload, 50) as payload_preview,
       created_at, updated_at
FROM financial_statements 
WHERE stock_symbol = 'AAPL' AND period_type = 'annual' AND statement_type = 'income_statement';

ROLLBACK;  -- Clean up the test data

-- 6. Show final table structure
\d financial_statements
