# Database Inspection Guide

This guide shows you how to inspect the SQLite database to verify data is being loaded correctly.

## Quick Commands

### View Table Summary
```bash
make inspect-db
```

### View Specific Table
```bash
make inspect-db TABLE=raw_market_data
make inspect-db TABLE=aggregated_indicators
make inspect-db TABLE=stock_news
make inspect-db TABLE=earnings_data
make inspect-db TABLE=industry_peers
```

### Run Custom SQL Query
```bash
make query-db QUERY="SELECT * FROM raw_market_data WHERE stock_symbol='AAPL' LIMIT 5;"
```

## Direct SQLite Commands

### Connect to Database
```bash
sqlite3 db/trading.db
```

### Useful SQLite Commands

Once connected to SQLite, you can use these commands:

```sql
-- List all tables
.tables

-- Show schema of a table
.schema raw_market_data

-- Show all data from a table (first 20 rows)
SELECT * FROM raw_market_data LIMIT 20;

-- Count rows in each table
SELECT 'raw_market_data' as table_name, COUNT(*) as count FROM raw_market_data
UNION ALL
SELECT 'aggregated_indicators', COUNT(*) FROM aggregated_indicators
UNION ALL
SELECT 'stock_news', COUNT(*) FROM stock_news
UNION ALL
SELECT 'earnings_data', COUNT(*) FROM earnings_data
UNION ALL
SELECT 'industry_peers', COUNT(*) FROM industry_peers;

-- Exit SQLite
.quit
```

## Useful Queries

### Check Market Data for a Symbol
```bash
make query-db QUERY="SELECT stock_symbol, date, close, volume FROM raw_market_data WHERE stock_symbol='AAPL' ORDER BY date DESC LIMIT 10;"
```

### Check Indicators for a Symbol
```bash
make query-db QUERY="SELECT stock_symbol, date, rsi, macd, signal FROM aggregated_indicators WHERE stock_symbol='AAPL' ORDER BY date DESC LIMIT 5;"
```

### Check News for a Symbol
```bash
make query-db QUERY="SELECT stock_symbol, title, publisher, published_date FROM stock_news WHERE stock_symbol='AAPL' ORDER BY published_date DESC LIMIT 5;"
```

### Check Earnings for a Symbol
```bash
make query-db QUERY="SELECT stock_symbol, earnings_date, eps_estimate, eps_actual, surprise_percentage FROM earnings_data WHERE stock_symbol='AAPL' ORDER BY earnings_date DESC LIMIT 5;"
```

### Check Industry Peers
```bash
make query-db QUERY="SELECT stock_symbol, peer_symbol, peer_name, peer_market_cap FROM industry_peers WHERE stock_symbol='AAPL' LIMIT 10;"
```

### Check Fundamentals (from JSON)
```bash
make query-db QUERY="SELECT stock_symbol, date, fundamental_data FROM raw_market_data WHERE stock_symbol='AAPL' AND fundamental_data IS NOT NULL ORDER BY date DESC LIMIT 1;"
```

### Check All Symbols with Data
```bash
make query-db QUERY="SELECT DISTINCT stock_symbol FROM raw_market_data ORDER BY stock_symbol;"
```

### Check Data Refresh Tracking
```bash
make query-db QUERY="SELECT stock_symbol, data_type, refresh_mode, last_refresh, status FROM data_refresh_tracking ORDER BY last_refresh DESC LIMIT 10;"
```

## Formatting Output

For better readability, use these SQLite options:

```bash
# Headers and column mode
sqlite3 -header -column db/trading.db "SELECT * FROM raw_market_data LIMIT 5;"

# CSV output
sqlite3 -csv db/trading.db "SELECT * FROM raw_market_data LIMIT 5;"

# JSON output
sqlite3 -json db/trading.db "SELECT * FROM raw_market_data LIMIT 5;"
```

## Docker Container Access

If you need to access the database from within a container:

```bash
# Access from go-api container
docker-compose exec go-api sqlite3 /app/db/trading.db ".tables"

# Access from python-worker container
docker-compose exec python-worker sqlite3 /app/db/trading.db ".tables"
```

## Common Issues

### Database file not found
```bash
# Check if database exists
ls -la db/trading.db

# If not found, initialize it
make init-db
```

### Permission denied
```bash
# Make scripts executable
chmod +x scripts/inspect_db.sh scripts/query_db.sh
```

### No data in tables
1. Check if data refresh was successful:
   ```bash
   curl -X POST http://localhost:8001/api/v1/refresh-data \
     -H "Content-Type: application/json" \
     -d '{"symbol": "AAPL", "data_types": ["price_historical", "fundamentals", "news"], "force": true}'
   ```

2. Check Python worker logs:
   ```bash
   docker-compose logs python-worker | tail -50
   ```

## Example Workflow

1. **Check if database exists and has tables:**
   ```bash
   make inspect-db
   ```

2. **Refresh data for a symbol:**
   ```bash
   curl -X POST http://localhost:8001/api/v1/refresh-data \
     -H "Content-Type: application/json" \
     -d '{"symbol": "AAPL", "data_types": ["price_historical", "fundamentals", "news", "earnings", "industry_peers"], "force": true}'
   ```

3. **Verify data was loaded:**
   ```bash
   make inspect-db TABLE=raw_market_data
   make inspect-db TABLE=stock_news
   make inspect-db TABLE=earnings_data
   ```

4. **Check specific symbol data:**
   ```bash
   make query-db QUERY="SELECT stock_symbol, COUNT(*) as rows FROM raw_market_data GROUP BY stock_symbol;"
   ```

