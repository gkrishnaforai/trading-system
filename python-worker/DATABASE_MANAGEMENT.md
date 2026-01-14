# Database Management Guide

This guide explains how to manage the trading system database, including initialization, migration, and troubleshooting.

## 🗄️ Database Schema Overview

The trading system uses PostgreSQL with the following key table groups:

### 1. **Core Tables**
- `stocks` - Master registry of all tradable symbols
- `missing_symbols_queue` - Queue for symbols that need to be added

### 2. **Market Data Tables**
- `raw_market_data_daily` - Daily OHLCV price data
- `raw_market_data_intraday` - Intraday OHLCV price data
- `indicators_daily` - Technical indicators (RSI, MACD, etc.)

### 3. **Fundamentals Tables**
- `fundamentals_summary` - Company overview and key metrics
- `fundamentals_snapshots` - JSON snapshots of fundamentals data
- `income_statements` - Income statement data
- `balance_sheets` - Balance sheet data
- `cash_flow_statements` - Cash flow data
- `financial_ratios` - Financial ratios and metrics

### 4. **Data Ingestion Tables**
- `data_ingestion_state` - Track loading status per symbol
- `data_ingestion_runs` - Track ingestion runs (audit trail)
- `data_ingestion_events` - Individual events with error details

### 5. **Industry & News Tables**
- `industry_peers` - Industry peer relationships
- `market_news` - Market news articles

### 6. **Signal Tables**
- `signals` - Trading signals from various engines

## 🚀 Quick Start - Complete Database Initialization

### Option 1: Using Safe Python Script (Recommended)

```bash
cd /Users/krishnag/tools/trading-system/python-worker

# Run the safe step-by-step initialization script
python init_database_safe.py

# Restart the python-worker service
docker-compose restart python-worker

# Test bulk loading
curl -X POST http://localhost:8001/api/v1/bulk/stocks/load/popular
```

### Option 2: Using Complete SQL Script

```bash
cd /Users/krishnag/tools/trading-system/python-worker

# Run the complete schema script
python init_database.py

# Restart the python-worker service
docker-compose restart python-worker

# Test bulk loading
curl -X POST http://localhost:8001/api/v1/bulk/stocks/load/popular
```

### Option 3: Using SQL Directly

```bash
cd /Users/krishnag/tools/trading-system/python-worker

# Connect to your PostgreSQL database
psql $DATABASE_URL

# Run the complete schema
\i migrations/init_database_complete.sql

# Exit psql
\q

# Restart services
docker-compose restart python-worker
```

## 🔄 Database Recreation Workflow

When you need to completely recreate the database (e.g., after removing PostgreSQL volume):

### 1. **Stop Services**
```bash
cd /Users/krishnag/tools/trading-system
docker-compose down
```

### 2. **Recreate Database Volume** (if needed)
```bash
# Remove PostgreSQL volume (WARNING: This deletes all data!)
docker volume rm trading-system_postgres_data

# Start services again
docker-compose up -d postgres
```

### 3. **Initialize Schema**
```bash
cd /Users/krishnag/tools/trading-system/python-worker
python init_database.py
```

### 4. **Start Application Services**
```bash
cd /Users/krishnag/tools/trading-system
docker-compose up -d python-worker streamlit
```

### 5. **Load Initial Data**
```bash
# Load popular stocks
curl -X POST http://localhost:8001/api/v1/bulk/stocks/load/popular

# Check progress
curl http://localhost:8001/api/v1/bulk/stocks/status/TASK_ID

# Verify stocks loaded
curl http://localhost:8001/api/v1/stocks/available
```

## 🛠️ Troubleshooting Common Issues

### Issue: "column 'symbol' does not exist"
**Cause**: Database schema not properly initialized
**Solution**: Run the complete initialization script
```bash
python init_database.py
```

### Issue: "relation 'data_ingestion_runs' does not exist"
**Cause**: Missing data ingestion tables
**Solution**: Ensure complete schema is loaded
```bash
psql $DATABASE_URL -c "\i migrations/init_database_complete.sql"
```

### Issue: "No module named 'scripts'" in bulk loading
**Cause**: Import path issues (should be fixed now)
**Solution**: Ensure Docker container is rebuilt with latest code
```bash
docker-compose build python-worker
docker-compose up -d python-worker
```

### Issue: HTTP 429 Rate Limiting from Yahoo Finance
**Cause**: Too many rapid requests during bulk loading
**Solution**: Rate limiting is now implemented, but if issues persist:
- Monitor progress with smaller batch sizes
- Consider loading in smaller batches manually

## 📊 Database Verification Commands

### Check All Tables Exist
```sql
SELECT table_name 
FROM information_schema.tables 
WHERE table_schema = 'public' 
ORDER BY table_name;
```

### Check Stocks Table
```sql
SELECT COUNT(*) as total_stocks FROM stocks;
SELECT symbol, company_name, sector FROM stocks LIMIT 10;
```

### Check Market Data
```sql
SELECT COUNT(*) as total_daily_records FROM raw_market_data_daily;
SELECT symbol, COUNT(*) as records FROM raw_market_data_daily GROUP BY symbol LIMIT 10;
```

### Check Recent Data Ingestion
```sql
SELECT * FROM data_ingestion_runs ORDER BY started_at DESC LIMIT 5;
SELECT symbol, table_name, last_ingested_at FROM data_ingestion_state ORDER BY last_ingested_at DESC LIMIT 10;
```

## 🔄 Migration Management

### Individual Migration Files
- `migrations/init_database_complete.sql` - Complete database schema
- `migrations/create_stocks_table.sql` - Stocks table only
- `migrations/create_alphavantage_tables.sql` - Alpha Vantage data tables
- `migrations/create_signal_tables.sql` - Signal tables
- `migrations/029_fix_column_naming_consistency.sql` - Column naming fixes

### Running Individual Migrations
```bash
psql $DATABASE_URL -c "\i migrations/create_stocks_table.sql"
psql $DATABASE_URL -c "\i migrations/create_alphavantage_tables.sql"
```

## 📝 Environment Variables

Required environment variables for database operations:

```bash
# Database connection
DATABASE_URL=postgresql://username:password@localhost:5432/trading_db

# Optional: Redis for caching
REDIS_URL=redis://localhost:6379/0
```

## 🚨 Important Notes

1. **Backup Before Recreation**: Always backup important data before recreating the database
2. **Volume Persistence**: PostgreSQL data is stored in Docker volumes - removing volumes deletes all data
3. **Sequential Loading**: Bulk loading is now rate-limited to avoid Yahoo Finance restrictions
4. **Schema Version**: The complete schema includes all necessary tables and relationships

## 🎯 Quick Test Sequence

After database initialization, run this sequence to verify everything works:

```bash
# 1. Test database summary
curl http://localhost:8001/api/v1/bulk/stocks/database/summary

# 2. Start bulk loading
curl -X POST http://localhost:8001/api/v1/bulk/stocks/load/popular

# 3. Monitor progress
curl http://localhost:8001/api/v1/bulk/stocks/status/TASK_ID

# 4. Verify stocks loaded
curl http://localhost:8001/api/v1/stocks/available

# 5. Test Streamlit UI
# Open browser to http://localhost:8501 and check Universal Backtest tab
```

This should resolve all database-related issues and provide a clean, reproducible database setup! 🚀📊✅
