# Test All Advanced Analysis Tabs - Complete Curl Commands

## Quick Test Script

```bash
# Run all endpoint tests at once
make test-endpoints SYMBOL=AAPL

# Or use the script directly
./scripts/test_all_endpoints.sh AAPL
```

## Individual Tab Tests

### 1. 📊 Moving Averages
```bash
curl "http://localhost:8000/api/v1/stock/AAPL?subscription_level=pro" | jq '.indicators | {
  ma7: .ma7,
  ma21: .ma21,
  sma50: .sma50,
  ema20: .ema20,
  ema50: .ema50,
  sma200: .sma200
}'
```

### 2. 📉 MACD & RSI
```bash
curl "http://localhost:8000/api/v1/stock/AAPL?subscription_level=pro" | jq '.indicators | {
  macd: .macd,
  macd_signal: .macd_signal,
  macd_histogram: .macd_histogram,
  rsi: .rsi
}'
```

### 3. 📈 Volume
```bash
# Get volume data (last 30 days)
curl "http://localhost:8000/api/v1/stock/AAPL/advanced-analysis?subscription_level=pro" | jq '.volume | .[0:10]'

# Get volume with dates
curl "http://localhost:8000/api/v1/stock/AAPL/advanced-analysis?subscription_level=pro" | jq '.volume | map({date, volume, price}) | .[0:5]'
```

### 4. 🧮 ATR & Volatility
```bash
curl "http://localhost:8000/api/v1/stock/AAPL/advanced-analysis?subscription_level=pro" | jq '.atr_volatility'
```

### 5. 🧠 AI Narrative
```bash
curl "http://localhost:8000/api/v1/llm_blog/AAPL" | jq '.content // .message'
```

### 6. 📚 Fundamentals
```bash
curl "http://localhost:8000/api/v1/stock/AAPL/fundamentals" | jq '{
  market_cap,
  pe_ratio,
  forward_pe,
  dividend_yield,
  eps,
  revenue,
  profit_margin,
  sector,
  industry
}'
```

### 7. 📰 News
```bash
curl "http://localhost:8000/api/v1/stock/AAPL/news" | jq '.news | .[0:5] | .[] | {title, publisher, published_date}'
```

### 8. 💰 Earnings
```bash
curl "http://localhost:8000/api/v1/stock/AAPL/earnings" | jq '.earnings | .[0:5]'
```

### 9. 🏭 Industry & Peers
```bash
curl "http://localhost:8000/api/v1/stock/AAPL/industry-peers" | jq '{
  sector,
  industry,
  peer_count: (.peers | length),
  peers: .peers | .[0:5] | map({symbol, name, market_cap})
}'
```

### 10. 📊 Comprehensive (All-in-One)
```bash
curl "http://localhost:8000/api/v1/stock/AAPL/advanced-analysis?subscription_level=pro" | jq
```

## Test Data Refresh with Error Tracking

### Refresh All Data Types
```bash
curl -X POST http://localhost:8001/api/v1/refresh-data \
  -H "Content-Type: application/json" \
  -d '{
    "symbol": "AAPL",
    "data_types": ["price_historical", "fundamentals", "news", "earnings", "industry_peers", "indicators"],
    "force": true
  }' | jq
```

### View Summary Only
```bash
curl -X POST http://localhost:8001/api/v1/refresh-data \
  -H "Content-Type: application/json" \
  -d '{
    "symbol": "AAPL",
    "data_types": ["price_historical", "fundamentals", "news", "earnings", "industry_peers", "indicators"],
    "force": true
  }' | jq '.summary'
```

### View Only Failed Items
```bash
curl -X POST http://localhost:8001/api/v1/refresh-data \
  -H "Content-Type: application/json" \
  -d '{
    "symbol": "AAPL",
    "data_types": ["price_historical", "fundamentals", "news", "earnings", "industry_peers", "indicators"],
    "force": true
  }' | jq '.results | to_entries | map(select(.value.status == "failed")) | from_entries'
```

### View Only Successful Items
```bash
curl -X POST http://localhost:8001/api/v1/refresh-data \
  -H "Content-Type: application/json" \
  -d '{
    "symbol": "AAPL",
    "data_types": ["price_historical", "fundamentals", "news", "earnings", "industry_peers", "indicators"],
    "force": true
  }' | jq '.results | to_entries | map(select(.value.status == "success")) | from_entries'
```

## Error Tracking in Database

### View Recent Errors
```bash
make query-db QUERY="SELECT stock_symbol, data_type, status, error_message, last_refresh FROM data_refresh_tracking WHERE status='failed' ORDER BY last_refresh DESC LIMIT 10;"
```

### View All Refresh History
```bash
make query-db QUERY="SELECT stock_symbol, data_type, refresh_mode, status, error_message, last_refresh FROM data_refresh_tracking ORDER BY last_refresh DESC LIMIT 20;"
```

## Complete Test Workflow

1. **Refresh data with error tracking:**
   ```bash
   curl -X POST http://localhost:8001/api/v1/refresh-data \
     -H "Content-Type: application/json" \
     -d '{
       "symbol": "AAPL",
       "data_types": ["price_historical", "fundamentals", "news", "earnings", "industry_peers", "indicators"],
       "force": true
     }' | jq '.summary'
   ```

2. **Test all endpoints:**
   ```bash
   make test-endpoints SYMBOL=AAPL
   ```

3. **Check database for errors:**
   ```bash
   make query-db QUERY="SELECT stock_symbol, data_type, status, error_message FROM data_refresh_tracking WHERE stock_symbol='AAPL' ORDER BY last_refresh DESC;"
   ```

4. **View in Streamlit:**
   - Open http://localhost:8501
   - Go to "Stock Analysis" page
   - Enter "AAPL"
   - Click "📥 Fetch Data" button
   - See detailed success/failure status
   - Expand "Advanced Analysis" to see all tabs

## Expected Response Format

All endpoints now return detailed status:

**Success Response:**
```json
{
  "status": "success",
  "message": "Data fetched successfully",
  "rows_affected": 250
}
```

**Failure Response:**
```json
{
  "status": "failed",
  "message": "No data available",
  "error": "Connection timeout to data source",
  "rows_affected": 0
}
```

**Skipped Response:**
```json
{
  "status": "skipped",
  "message": "Data is fresh, no refresh needed"
}
```

