-- SQL commands to verify data loaded by the Massive.com integration test
-- Connect to your Postgres container and run these to see rows in the new schema tables.

-- 1) Daily market data rows per symbol
SELECT 
  stock_symbol,
  COUNT(*) AS daily_rows,
  MIN(trade_date) AS earliest,
  MAX(trade_date) AS latest
FROM raw_market_data_daily
GROUP BY stock_symbol
ORDER BY stock_symbol;

-- 2) Indicators daily rows per symbol
SELECT 
  stock_symbol,
  COUNT(*) AS indicator_rows,
  MIN(trade_date) AS earliest,
  MAX(trade_date) AS latest
FROM indicators_daily
GROUP BY stock_symbol
ORDER BY stock_symbol;

-- 3) Fundamentals snapshots per symbol
SELECT 
  stock_symbol,
  COUNT(*) AS fundamentals_rows,
  MAX(updated_at) AS last_updated
FROM fundamentals_snapshots
GROUP BY stock_symbol
ORDER BY stock_symbol;

-- 4) Industry peers per symbol
SELECT 
  stock_symbol,
  COUNT(*) AS peers_count,
  STRING_AGG(DISTINCT peer_symbol, ', ' ORDER BY peer_symbol) AS peers
FROM industry_peers
GROUP BY stock_symbol
ORDER BY stock_symbol;

-- 5) Data ingestion state tracking
SELECT 
  stock_symbol,
  dataset,
  source,
  status,
  last_success_at,
  error_message
FROM data_ingestion_state
ORDER BY stock_symbol, dataset;

-- 6) Sample rows from raw_market_data_daily
SELECT *
FROM raw_market_data_daily
WHERE stock_symbol = 'AAPL'
ORDER BY trade_date DESC
LIMIT 5;

-- 7) Sample rows from indicators_daily
SELECT 
  stock_symbol,
  trade_date,
  ema9,
  ema21,
  sma50,
  sma200,
  rsi,
  macd,
  atr,
  source
FROM indicators_daily
WHERE stock_symbol = 'AAPL'
ORDER BY trade_date DESC
LIMIT 5;

-- 8) Sample fundamentals snapshot
SELECT *
FROM fundamentals_snapshots
WHERE stock_symbol = 'AAPL'
ORDER BY updated_at DESC
LIMIT 1;

-- 9) Check for duplicates (should be none due to ON CONFLICT)
SELECT 
  stock_symbol,
  trade_date,
  COUNT(*) AS dupes
FROM raw_market_data_daily
GROUP BY stock_symbol, trade_date
HAVING COUNT(*) > 1;

-- 10) Table sizes (row counts)
SELECT 
  schemaname,
  tablename,
  n_tup_ins AS inserts,
  n_tup_upd AS updates,
  n_tup_del AS deletes,
  n_live_tup AS live_rows,
  n_dead_tup AS dead_rows
FROM pg_stat_user_tables
WHERE schemaname = 'public'
  AND tablename IN (
    'raw_market_data_daily',
    'indicators_daily',
    'fundamentals_snapshots',
    'industry_peers',
    'data_ingestion_state'
  )
ORDER BY tablename;
