# API Endpoints with Error Handling

All endpoints now return detailed status information showing what succeeded and what failed.

## Refresh Data Endpoint (Enhanced)

### POST `/api/v1/refresh-data`

**Request:**
```json
{
  "symbol": "AAPL",
  "data_types": ["price_historical", "fundamentals", "news", "earnings", "industry_peers", "indicators"],
  "force": false
}
```

**Response (Success):**
```json
{
  "symbol": "AAPL",
  "summary": {
    "total_requested": 6,
    "total_successful": 5,
    "total_failed": 1,
    "total_skipped": 0
  },
  "results": {
    "price_historical": {
      "data_type": "price_historical",
      "status": "success",
      "message": "Successfully fetched 250 rows of historical price data",
      "rows_affected": 250,
      "error": null,
      "timestamp": "2025-12-21T22:30:00"
    },
    "fundamentals": {
      "data_type": "fundamentals",
      "status": "success",
      "message": "Fundamentals updated",
      "error": null,
      "timestamp": "2025-12-21T22:30:01"
    },
    "news": {
      "data_type": "news",
      "status": "success",
      "message": "Fetched 20 news articles",
      "rows_affected": 20,
      "error": null,
      "timestamp": "2025-12-21T22:30:02"
    },
    "earnings": {
      "data_type": "earnings",
      "status": "failed",
      "message": "No earnings data found",
      "rows_affected": 0,
      "error": "No earnings data available",
      "timestamp": "2025-12-21T22:30:03"
    },
    "industry_peers": {
      "data_type": "industry_peers",
      "status": "success",
      "message": "Industry peers updated",
      "error": null,
      "timestamp": "2025-12-21T22:30:04"
    },
    "indicators": {
      "data_type": "indicators",
      "status": "success",
      "message": "Indicators calculated successfully",
      "error": null,
      "timestamp": "2025-12-21T22:30:05"
    }
  }
}
```

**Response (All Failed):**
```json
{
  "symbol": "AAPL",
  "summary": {
    "total_requested": 6,
    "total_successful": 0,
    "total_failed": 6,
    "total_skipped": 0
  },
  "results": {
    "price_historical": {
      "data_type": "price_historical",
      "status": "failed",
      "message": "Exception: Connection timeout",
      "error": "Connection timeout",
      "timestamp": "2025-12-21T22:30:00"
    }
  }
}
```

## Test Commands

### Test All Data Types
```bash
curl -X POST http://localhost:8001/api/v1/refresh-data \
  -H "Content-Type: application/json" \
  -d '{
    "symbol": "AAPL",
    "data_types": ["price_historical", "fundamentals", "news", "earnings", "industry_peers", "indicators"],
    "force": true
  }' | jq
```

### Test Individual Data Types
```bash
# Price only
curl -X POST http://localhost:8001/api/v1/refresh-data \
  -H "Content-Type: application/json" \
  -d '{"symbol": "AAPL", "data_types": ["price_historical"], "force": true}' | jq

# Fundamentals only
curl -X POST http://localhost:8001/api/v1/refresh-data \
  -H "Content-Type: application/json" \
  -d '{"symbol": "AAPL", "data_types": ["fundamentals"], "force": true}' | jq
```

### View Error Summary
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

## Error Tracking in Database

Errors are automatically tracked in the `data_refresh_tracking` table:

```sql
SELECT 
    stock_symbol,
    data_type,
    refresh_mode,
    status,
    error_message,
    last_refresh
FROM data_refresh_tracking
WHERE stock_symbol = 'AAPL'
ORDER BY last_refresh DESC;
```

## Streamlit UI Display

The Streamlit UI now shows:
- ✅ Success count
- ❌ Failure count
- ⏭️ Skipped count
- Detailed error messages for each failed data type
- Expandable section with full results

## Error Handling Features

1. **Exception Catching**: All refresh operations are wrapped in try/except
2. **Error Messages**: Detailed error messages for each failure
3. **Status Tracking**: Each data type has a status (success/failed/skipped)
4. **Database Logging**: Errors are logged to `data_refresh_tracking` table
5. **UI Display**: Streamlit shows what succeeded and what failed
6. **Retry Logic**: Can force refresh even if data is fresh

