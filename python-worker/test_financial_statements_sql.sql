-- PostgreSQL SQL Test for Financial Statements
-- Run these commands directly in psql or your PostgreSQL client

-- 1. Check if table exists and show schema
\dt financial_statements
\d financial_statements

-- 2. Show all constraints on the table
SELECT conname, contype, pg_get_constraintdef(oid) as definition
FROM pg_constraint 
WHERE conrelid = 'financial_statements'::regclass;

-- 3. Test simple insert (minimal data)
BEGIN;
INSERT INTO financial_statements 
(stock_symbol, period_type, statement_type, fiscal_period)
VALUES ('TEST', 'annual', 'income_statement', '2026-12-31');
ROLLBACK;

-- 4. Test full insert with exact same data as application
BEGIN;
INSERT INTO financial_statements 
(stock_symbol, period_type, statement_type, fiscal_period, payload, data_source, created_at, updated_at)
VALUES (
    'AAPL', 
    'annual', 
    'income_statement', 
    '2026-12-31',
    '{"date": "2021-09-25", "symbol": "AAPL", "reportedCurrency": "USD", "cik": "0000320193", "filingDate": "2021-10-29", "acceptedDate": "2021-10-28 18:00:00", "revenue": 365817000000, "costOfRevenue": 209136000000, "grossProfit": 156681000000, "grossProfitMargin": 0.43, "researchAndDevelopmentExpenses": 21914000000, "generalAndAdministrativeExpenses": 25049000000, "sellingAndMarketingExpenses": 26980000000, "otherExpenses": 0, "operatingExpenses": 283030000000, "costAndExpenses": 283030000000, "interestIncome": 2681000000, "interestExpense": 2931000000, "depreciationAndAmortization": 0, "ebitda": 82787000000, "ebitdaratio": 0.23, "operatingIncome": 82787000000, "operatingIncomeRatio": 0.23, "totalOtherIncomeExpensesNet": -248000000, "incomeBeforeTax": 82539000000, "incomeBeforeTaxRatio": 0.23, "incomeTaxExpense": 13855000000, "netIncome": 94680000000, "netIncomeRatio": 0.26, "eps": 5.67, "epsdiluted": 5.61, "weightedAverageShsOut": 16701272000, "weightedAverageShsOutDil": 16864919000}',
    'unknown',
    '2026-01-21 05:57:03',
    '2026-01-21 05:57:03'
);
ROLLBACK;

-- 5. Test with ON CONFLICT clause (exact same as application)
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
ROLLBACK;

-- 6. If table doesn't exist, create it
CREATE TABLE IF NOT EXISTS financial_statements (
    stock_symbol VARCHAR(20) NOT NULL,
    period_type VARCHAR(20) NOT NULL,
    statement_type VARCHAR(50) NOT NULL,
    fiscal_period DATE NOT NULL,
    payload TEXT,
    data_source VARCHAR(50),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (stock_symbol, period_type, statement_type, fiscal_period)
);

-- 7. If table exists but missing columns, add them
ALTER TABLE financial_statements 
ADD COLUMN IF NOT EXISTS payload TEXT,
ADD COLUMN IF NOT EXISTS data_source VARCHAR(50),
ADD COLUMN IF NOT EXISTS created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP;

-- 8. Add primary key constraint if missing
ALTER TABLE financial_statements 
ADD CONSTRAINT IF NOT EXISTS financial_statements_pkey 
PRIMARY KEY (stock_symbol, period_type, statement_type, fiscal_period);

-- 9. Test again after fixes
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
    NOW(),
    NOW()
)
ON CONFLICT (stock_symbol, period_type, statement_type, fiscal_period)
DO UPDATE SET
    payload = EXCLUDED.payload,
    data_source = EXCLUDED.data_source,
    updated_at = NOW();
ROLLBACK;
