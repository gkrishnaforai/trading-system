# Fix: Data Showing Zeros in Database

## Problem
The database shows zeros for price, volume, and indicators. This means data wasn't fetched or calculated correctly.

## Solution: Re-fetch and Calculate Data

### Step 1: Re-fetch Historical Data with Indicators

```bash
# Option 1: Use the refresh API endpoint (recommended)
curl -X POST http://localhost:8001/api/v1/refresh-data \
  -H "Content-Type: application/json" \
  -d '{
    "symbol": "AAPL",
    "data_types": ["price_historical", "indicators"],
    "force": true
  }'
```

### Step 2: Verify Data Was Loaded

```bash
# Check raw market data
make query-db QUERY="SELECT stock_symbol, date, close, volume FROM raw_market_data WHERE stock_symbol='AAPL' ORDER BY date DESC LIMIT 5;"

# Check indicators
make query-db QUERY="SELECT stock_symbol, date, ma7, sma50, rsi, macd FROM aggregated_indicators WHERE stock_symbol='AAPL' ORDER BY date DESC LIMIT 1;"
```

### Step 3: If Data Still Shows Zeros

The issue might be in how data is being saved. Check:

1. **Python worker logs:**
   ```bash
   docker-compose logs python-worker | tail -50
   ```

2. **Manually trigger data fetch:**
   ```bash
   docker-compose exec python-worker python -c "
   from app.database import init_database
   from app.services.data_fetcher import DataFetcher
   from app.services.indicator_service import IndicatorService
   
   init_database()
   df = DataFetcher()
   success = df.fetch_and_save_stock('AAPL', period='1y')
   print(f'Data fetch: {success}')
   
   if success:
       is_service = IndicatorService()
       calc_success = is_service.calculate_indicators('AAPL')
       print(f'Indicators calculated: {calc_success}')
   "
   ```

### Step 4: Check Data Source

If Yahoo Finance is returning data but it's being saved as zeros, check:

```bash
# Test Yahoo Finance directly
docker-compose exec python-worker python -c "
import yfinance as yf
ticker = yf.Ticker('AAPL')
data = ticker.history(period='5d')
print(data[['Close', 'Volume']].tail())
"
```

## Quick Fix Script

Save this as `fix_data.sh`:

```bash
#!/bin/bash
SYMBOL="${1:-AAPL}"

echo "🔄 Re-fetching data for $SYMBOL..."

# Refresh data
curl -X POST http://localhost:8001/api/v1/refresh-data \
  -H "Content-Type: application/json" \
  -d "{
    \"symbol\": \"$SYMBOL\",
    \"data_types\": [\"price_historical\", \"indicators\"],
    \"force\": true
  }"

echo ""
echo "⏳ Waiting 5 seconds for processing..."
sleep 5

echo ""
echo "✅ Verifying data:"
make query-db QUERY="SELECT stock_symbol, date, close, volume FROM raw_market_data WHERE stock_symbol='$SYMBOL' AND close > 0 ORDER BY date DESC LIMIT 3;"
```

## Common Issues

1. **Data fetched but not saved**: Check Python worker logs for errors
2. **Indicators not calculated**: Ensure `calculate_indicators` is called after data fetch
3. **Yahoo Finance API issues**: Check if yfinance is working correctly
4. **Database connection issues**: Verify database path is correct

