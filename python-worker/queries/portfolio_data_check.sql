-- ========================================
-- PORTFOLIO DATA INTEGRITY CHECK
-- Shows where data is stored across tables
-- ========================================

-- 1. Check users table
SELECT 'USERS' as table_name, COUNT(*) as record_count, 
       string_agg(username, ', ' ORDER BY username) as sample_data
FROM users;

-- 2. Check portfolios table  
SELECT 'PORTFOLIOS' as table_name, COUNT(*) as record_count,
       string_agg(name || ' (' || id::text || ')', ', ' ORDER BY name) as sample_data
FROM portfolios;

-- 3. Check portfolio_holdings table
SELECT 'PORTFOLIO_HOLDINGS' as table_name, COUNT(*) as record_count,
       string_agg(symbol || ' (' || portfolio_id::text || ')', ', ' ORDER BY symbol) as sample_data
FROM portfolio_holdings;

-- 4. Check stocks table (master reference)
SELECT 'STOCKS' as table_name, COUNT(*) as record_count,
       string_agg(symbol || ' - ' || company_name, ', ' ORDER BY symbol) as sample_data
FROM stocks 
WHERE is_active = true
LIMIT 10;

-- 5. Show portfolio holdings with stock info
SELECT 
    ph.portfolio_id,
    p.name as portfolio_name,
    ph.symbol,
    s.company_name,
    s.exchange,
    s.sector,
    ph.shares_held,
    ph.average_cost,
    ph.status,
    ph.created_at as holding_created
FROM portfolio_holdings ph
INNER JOIN portfolios p ON ph.portfolio_id = p.id
LEFT JOIN stocks s ON ph.symbol = s.symbol
ORDER BY p.name, ph.symbol;

-- 6. Show foreign key relationships
SELECT 
    tc.table_name, 
    tc.constraint_name, 
    tc.constraint_type,
    kcu.column_name,
    ccu.table_name AS foreign_table_name,
    ccu.column_name AS foreign_column_name 
FROM information_schema.table_constraints AS tc 
JOIN information_schema.key_column_usage AS kcu
    ON tc.constraint_name = kcu.constraint_name
    AND tc.table_schema = kcu.table_schema
JOIN information_schema.constraint_column_usage AS ccu
    ON ccu.constraint_name = tc.constraint_name
    AND ccu.table_schema = tc.table_schema
WHERE tc.constraint_type = 'FOREIGN KEY' 
    AND tc.table_name IN ('users', 'portfolios', 'portfolio_holdings', 'stocks');

-- 7. Check data consistency
SELECT 
    'Orphaned Holdings' as issue,
    COUNT(*) as count
FROM portfolio_holdings ph
LEFT JOIN stocks s ON ph.symbol = s.symbol
WHERE s.symbol IS NULL

UNION ALL

SELECT 
    'Holdings with Invalid Portfolios' as issue,
    COUNT(*) as count
FROM portfolio_holdings ph
LEFT JOIN portfolios p ON ph.portfolio_id = p.id
WHERE p.id IS NULL

UNION ALL

SELECT 
    'Portfolios without Users' as issue,
    COUNT(*) as count
FROM portfolios p
LEFT JOIN users u ON p.user_id = u.id
WHERE u.id IS NULL;
