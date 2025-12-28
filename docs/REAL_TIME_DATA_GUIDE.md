# Real-Time Data Guide

## Overview

The trading system supports real-time/live data fetching for stock prices and other market data. This guide explains how to enable and use real-time data features.

## Architecture

### Components

1. **PeriodicWorker** (`python-worker/app/workers/periodic_worker.py`)
   - Handles periodic and live data updates
   - Runs in background thread
   - Supports both periodic (15 min intervals) and live (1 min intervals) updates

2. **LiveRefreshStrategy** (`python-worker/app/data_management/refresh_strategy.py`)
   - Strategy for real-time data refresh
   - Max age: 1 minute (configurable)
   - Highest priority (200)

3. **live_prices Table** (`db/migrations/003_add_news_earnings_industry.sql`)
   - Stores real-time price snapshots
   - Tracks price changes and timestamps
   - Indexed for fast queries

4. **DataRefreshManager** (`python-worker/app/data_management/refresh_manager.py`)
   - Orchestrates data fetching
   - Saves to `live_prices` table
   - Tracks refresh status

## Enabling Real-Time Updates

### Environment Variable

Set `ENABLE_LIVE_UPDATES=true` in your environment or `.env` file:

```bash
export ENABLE_LIVE_UPDATES=true
```

Or in `.env`:
```
ENABLE_LIVE_UPDATES=true
```

### Starting the Periodic Worker

The periodic worker runs separately from the batch worker:

```bash
# In python-worker directory
python -m app.workers.periodic_worker
```

Or via Docker Compose (add to `docker-compose.yml`):
```yaml
periodic-worker:
  build: ./python-worker
  command: python -m app.workers.periodic_worker
  environment:
    - ENABLE_LIVE_UPDATES=true
  depends_on:
    - db
    - redis
```

## Refresh Intervals

### Periodic Updates (Always Enabled)

| Data Type | Interval | Description |
|-----------|----------|-------------|
| `PRICE_CURRENT` | 15 minutes | Current stock prices |
| `NEWS` | 1 hour | Recent news articles |
| `EARNINGS` | 6 hours | Earnings calendar |
| `FUNDAMENTALS` | 12 hours | Fundamental metrics |

### Live Updates (Requires `ENABLE_LIVE_UPDATES=true`)

| Data Type | Interval | Description |
|-----------|----------|-------------|
| `PRICE_CURRENT` | 1 minute | Real-time stock prices |

**Note:** Live updates are limited to top 5 most active symbols to prevent API rate limits.

## API Endpoints

### Get Live Price for Single Symbol

```bash
GET /api/v1/live-price/{symbol}
```

**Example:**
```bash
curl http://localhost:8001/api/v1/live-price/AAPL
```

**Response:**
```json
{
  "symbol": "AAPL",
  "price": 175.43,
  "change": 0.52,
  "change_percent": 0.30,
  "timestamp": "2025-12-22T11:30:00",
  "source": "database"
}
```

### Get Live Prices for Multiple Symbols

```bash
GET /api/v1/live-prices?symbols=AAPL,GOOGL,NVDA
```

**Example:**
```bash
curl "http://localhost:8001/api/v1/live-prices?symbols=AAPL,GOOGL,NVDA"
```

**Response:**
```json
{
  "prices": [
    {
      "symbol": "AAPL",
      "price": 175.43,
      "change": 0.52,
      "change_percent": 0.30,
      "timestamp": "2025-12-22T11:30:00",
      "source": "database"
    },
    {
      "symbol": "GOOGL",
      "price": 142.15,
      "change": -0.25,
      "change_percent": -0.18,
      "timestamp": "2025-12-22T11:30:00",
      "source": "database"
    }
  ],
  "count": 2,
  "timestamp": "2025-12-22T11:30:00"
}
```

### Get All Live Prices (from Holdings)

```bash
GET /api/v1/live-prices
```

Returns live prices for all symbols in user holdings.

### Manually Refresh Live Price

```bash
POST /api/v1/refresh-live-price/{symbol}
```

**Example:**
```bash
curl -X POST http://localhost:8001/api/v1/refresh-live-price/AAPL
```

**Response:**
```json
{
  "message": "Live price refreshed for AAPL",
  "symbol": "AAPL",
  "success": true
}
```

## Database Schema

### live_prices Table

```sql
CREATE TABLE live_prices (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    stock_symbol TEXT NOT NULL,
    price REAL NOT NULL,
    change REAL,                    -- Price change from previous
    change_percent REAL,             -- Price change percentage
    volume INTEGER,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(stock_symbol, timestamp)
);
```

### Querying Live Prices

```sql
-- Get latest price for a symbol
SELECT price, change, change_percent, timestamp
FROM live_prices
WHERE stock_symbol = 'AAPL'
ORDER BY timestamp DESC
LIMIT 1;

-- Get price history for a symbol (last hour)
SELECT price, change, change_percent, timestamp
FROM live_prices
WHERE stock_symbol = 'AAPL'
  AND timestamp >= datetime('now', '-1 hour')
ORDER BY timestamp DESC;

-- Get all latest prices
SELECT DISTINCT ON (stock_symbol) 
    stock_symbol, price, change, change_percent, timestamp
FROM live_prices
ORDER BY stock_symbol, timestamp DESC;
```

## How It Works

### Data Flow

```
1. PeriodicWorker starts (if ENABLE_LIVE_UPDATES=true)
   ↓
2. Every minute, checks which symbols need live updates
   ↓
3. Fetches current price from Yahoo Finance API
   ↓
4. Calculates price change from previous price
   ↓
5. Saves to live_prices table
   ↓
6. Also updates raw_market_data for compatibility
```

### Active Symbols

Live updates are automatically enabled for:
- All symbols in user holdings
- Top 5 most active symbols (to prevent rate limits)

### Rate Limiting

- **Periodic updates**: Limited to 10 symbols per cycle
- **Live updates**: Limited to 5 symbols per cycle
- **API calls**: Respects Yahoo Finance rate limits

## Integration with Streamlit UI

### Displaying Live Prices

```python
import streamlit as st
import requests

# Fetch live price
response = requests.get(f"http://localhost:8001/api/v1/live-price/AAPL")
if response.status_code == 200:
    data = response.json()
    st.metric(
        label="AAPL",
        value=f"${data['price']:.2f}",
        delta=f"{data['change_percent']:.2f}%" if data['change_percent'] else None
    )
```

### Auto-Refresh in Streamlit

```python
import time

# Auto-refresh every 30 seconds
if st.button("Enable Live Updates"):
    placeholder = st.empty()
    while True:
        response = requests.get("http://localhost:8001/api/v1/live-prices?symbols=AAPL,GOOGL")
        if response.status_code == 200:
            data = response.json()
            placeholder.json(data)
        time.sleep(30)
```

## Monitoring

### Check if Live Updates are Running

```bash
# Check logs
docker logs trading-system-python-worker | grep "Live update"

# Check database
sqlite3 db/trading.db "SELECT COUNT(*) FROM live_prices WHERE timestamp >= datetime('now', '-1 hour');"
```

### Verify Live Prices Table

```bash
# View recent live prices
sqlite3 db/trading.db "SELECT * FROM live_prices ORDER BY timestamp DESC LIMIT 10;"

# Check refresh tracking
sqlite3 db/trading.db "SELECT * FROM data_refresh_tracking WHERE refresh_mode = 'live' ORDER BY last_refresh DESC LIMIT 10;"
```

## Performance Considerations

### Database Size

- `live_prices` table can grow quickly
- Consider archiving old data (> 24 hours)
- Use indexes for fast queries

### API Rate Limits

- Yahoo Finance has rate limits
- Live updates limited to 5 symbols
- Adjust intervals if hitting limits

### Memory Usage

- Periodic worker runs in background thread
- Minimal memory footprint
- Can run alongside batch worker

## Troubleshooting

### Live Updates Not Working

1. **Check environment variable:**
   ```bash
   echo $ENABLE_LIVE_UPDATES
   ```

2. **Check periodic worker is running:**
   ```bash
   ps aux | grep periodic_worker
   ```

3. **Check logs:**
   ```bash
   docker logs trading-system-python-worker | grep -i "live\|periodic"
   ```

4. **Verify database:**
   ```bash
   sqlite3 db/trading.db "SELECT COUNT(*) FROM live_prices;"
   ```

### No Data in live_prices Table

- Ensure periodic worker is running
- Check `ENABLE_LIVE_UPDATES=true`
- Verify symbols exist in holdings
- Check API connectivity

### Rate Limit Errors

- Reduce live update frequency
- Reduce number of symbols
- Use periodic updates instead of live

## Future Enhancements

### WebSocket Support (Planned)

Real-time streaming via WebSocket:
```javascript
const ws = new WebSocket('ws://localhost:8001/ws/live-prices');
ws.onmessage = (event) => {
  const data = JSON.parse(event.data);
  console.log('Live price:', data);
};
```

### Redis Pub/Sub (Planned)

Publish live prices to Redis for distributed systems:
```python
redis.publish('live_prices:AAPL', json.dumps(price_data))
```

### Market Data Providers (Planned)

Support for professional data providers:
- Alpha Vantage
- Polygon.io
- IEX Cloud
- Finnhub

## Summary

✅ **Real-time data is supported** via:
- Periodic worker with live mode
- `live_prices` database table
- API endpoints for fetching live prices
- Automatic updates every 1 minute (when enabled)

🔧 **To enable:**
1. Set `ENABLE_LIVE_UPDATES=true`
2. Start periodic worker
3. Use API endpoints to fetch live prices

📊 **Data is stored in:**
- `live_prices` table (real-time snapshots)
- `raw_market_data` table (daily compatibility)

