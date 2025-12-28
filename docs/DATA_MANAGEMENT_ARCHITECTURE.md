# Data Management Architecture

## Overview

The Trading System implements a comprehensive data management architecture that supports multiple refresh modes: **scheduled**, **on-demand**, **periodic**, and **live/real-time**. This architecture follows DRY and SOLID principles, making it extensible and maintainable.

## Architecture Components

### 1. Data Source Abstraction Layer (Strategy Pattern)

**Location**: `python-worker/app/data_sources/`

- **BaseDataSource**: Abstract interface for all data providers
- **YahooFinanceSource**: Yahoo Finance implementation (primary provider)
- **Future**: Alpha Vantage, Polygon.io, IEX Cloud, etc.

**Benefits**:
- Easy to swap data providers
- Consistent interface across providers
- Supports multiple providers simultaneously

### 2. Data Refresh Strategies

**Location**: `python-worker/app/data_management/refresh_strategy.py`

#### Refresh Modes

1. **SCHEDULED** (`ScheduledRefreshStrategy`)
   - Cron-based refresh (e.g., 1 AM daily)
   - Used for: Historical data, fundamentals, indicators, signals, reports
   - Priority: Based on data type importance

2. **ON_DEMAND** (`OnDemandRefreshStrategy`)
   - User-triggered refresh
   - Used for: Any data type when user requests it
   - Priority: Highest (100) - user-requested data

3. **PERIODIC** (`PeriodicRefreshStrategy`)
   - Regular interval refresh (e.g., every 15 minutes)
   - Used for: Current prices, news, earnings updates
   - Priority: Medium (5-20) based on data type

4. **LIVE** (`LiveRefreshStrategy`)
   - Real-time updates (e.g., every 1 minute)
   - Used for: Current prices, breaking news
   - Priority: Highest (200) - real-time data

### 3. Data Refresh Manager

**Location**: `python-worker/app/data_management/refresh_manager.py`

Central orchestrator that:
- Manages refresh strategies
- Tracks last refresh times
- Determines when data needs refreshing
- Executes refreshes based on mode and data type

### 4. Data Types

**Location**: `python-worker/app/data_management/refresh_strategy.py` (DataType enum)

Supported data types:
- `PRICE_HISTORICAL`: Historical OHLCV data
- `PRICE_CURRENT`: Current/live price
- `FUNDAMENTALS`: Fundamental metrics (P/E, revenue, etc.)
- `NEWS`: Recent news articles
- `EARNINGS`: Earnings calendar and history
- `INDUSTRY_PEERS`: Industry and peer data
- `INDICATORS`: Technical indicators (MACD, RSI, etc.)
- `SIGNALS`: Trading signals
- `REPORTS`: LLM-generated reports

## Data Refresh Flow

### Scheduled Refresh (Nightly Batch)

**Worker**: `BatchWorker` (`python-worker/app/workers/batch_worker.py`)

**Schedule**: 1:00 AM daily (configurable)

**Process**:
1. Get all symbols from holdings
2. Refresh historical price data
3. Refresh fundamentals
4. Refresh news
5. Refresh earnings
6. Refresh industry/peers
7. Calculate indicators
8. Generate portfolio signals
9. Generate stock reports

### Periodic Refresh

**Worker**: `PeriodicWorker` (`python-worker/app/workers/periodic_worker.py`)

**Intervals**:
- Current prices: Every 15 minutes
- News: Every 1 hour
- Earnings: Every 6 hours
- Fundamentals: Every 12 hours

**Process**:
- Runs in background thread
- Checks which symbols need refreshing
- Refreshes data based on intervals
- Limits concurrent refreshes to prevent API rate limits

### Live/Real-Time Refresh

**Worker**: `PeriodicWorker` (with live mode enabled)

**Intervals**:
- Current prices: Every 1 minute

**Process**:
- Only enabled when `ENABLE_LIVE_UPDATES=true`
- Refreshes top 5 most active symbols
- Prevents API rate limits

### On-Demand Refresh

**API Endpoint**: `POST /api/v1/refresh-data`

**Request**:
```json
{
  "symbol": "AAPL",
  "data_types": ["price_historical", "fundamentals", "news"],
  "force": false
}
```

**Response**:
```json
{
  "success": true,
  "symbol": "AAPL",
  "results": {
    "price_historical": true,
    "fundamentals": true,
    "news": true
  },
  "message": "Refreshed 3/3 data types for AAPL"
}
```

## Database Schema

### New Tables (Migration 003)

1. **stock_news**: News articles with sentiment scores
2. **earnings_data**: Earnings calendar and history
3. **industry_peers**: Industry and peer relationships
4. **data_refresh_tracking**: Tracks when each data type was last refreshed
5. **live_prices**: Real-time price updates

### Existing Tables (Enhanced)

- **raw_market_data**: Now includes `news_metadata` JSON field
- **aggregated_indicators**: Technical indicators (unchanged)

## API Endpoints

### On-Demand Data Refresh

**POST** `/api/v1/refresh-data`
- Refresh specific data types for a symbol
- Supports all data types
- Can force refresh even if data is fresh

**POST** `/api/v1/fetch-historical-data` (Legacy)
- Backward compatible endpoint
- Uses refresh manager internally

### Health Check

**GET** `/health`
- Service health status

## Configuration

**Environment Variables**:
- `ENABLE_LIVE_UPDATES`: Enable live/real-time updates (default: false)
- `BATCH_SCHEDULE_HOUR`: Hour for scheduled batch (default: 1)
- `BATCH_SCHEDULE_MINUTE`: Minute for scheduled batch (default: 0)

## Usage Examples

### Scheduled Refresh (Automatic)

The batch worker automatically runs at 1 AM daily. No action needed.

### On-Demand Refresh (API)

```python
import requests

# Refresh all data types for a symbol
response = requests.post(
    "http://python-worker:8001/api/v1/refresh-data",
    json={
        "symbol": "AAPL",
        "data_types": None,  # None = all types
        "force": False
    }
)

# Refresh specific data types
response = requests.post(
    "http://python-worker:8001/api/v1/refresh-data",
    json={
        "symbol": "AAPL",
        "data_types": ["price_current", "news"],
        "force": True
    }
)
```

### On-Demand Refresh (Python)

```python
from app.data_management.refresh_manager import DataRefreshManager
from app.data_management.refresh_strategy import RefreshMode, DataType

manager = DataRefreshManager()

# Refresh all data types
results = manager.refresh_data(
    symbol="AAPL",
    data_types=[
        DataType.PRICE_HISTORICAL,
        DataType.FUNDAMENTALS,
        DataType.NEWS,
        DataType.EARNINGS,
        DataType.INDUSTRY_PEERS,
    ],
    mode=RefreshMode.ON_DEMAND,
    force=False
)
```

## Features Supported

### ✅ Moving Averages
- **Data Source**: Historical price data
- **Refresh**: Scheduled (daily), On-demand
- **Calculation**: Automatic after price data refresh

### ✅ MACD & RSI
- **Data Source**: Historical price data
- **Refresh**: Scheduled (daily), On-demand
- **Calculation**: Automatic after price data refresh

### ✅ Volume
- **Data Source**: Historical price data (includes volume)
- **Refresh**: Scheduled (daily), On-demand
- **Calculation**: Volume MA calculated with indicators

### ✅ ATR & Volatility
- **Data Source**: Historical price data (OHLC)
- **Refresh**: Scheduled (daily), On-demand
- **Calculation**: ATR and Bollinger Bands calculated with indicators

### ✅ AI Narrative
- **Data Source**: Indicators + LLM
- **Refresh**: Scheduled (daily), On-demand
- **Generation**: LLM agent generates narratives from indicators

### ✅ Fundamentals
- **Data Source**: Yahoo Finance `ticker.info`
- **Refresh**: Scheduled (daily), Periodic (12h), On-demand
- **Storage**: JSON in `raw_market_data.fundamental_data`

### ✅ Industry & Peers
- **Data Source**: Yahoo Finance sector/industry data
- **Refresh**: Scheduled (daily), Periodic (12h), On-demand
- **Storage**: `industry_peers` table + JSON in `raw_market_data.fundamental_data`

### ✅ News
- **Data Source**: Yahoo Finance `ticker.news`
- **Refresh**: Scheduled (daily), Periodic (1h), On-demand
- **Storage**: `stock_news` table + JSON in `raw_market_data.news_metadata`

### ✅ Earnings
- **Data Source**: Yahoo Finance `ticker.calendar`
- **Refresh**: Scheduled (daily), Periodic (6h), On-demand
- **Storage**: `earnings_data` table

### ✅ Current Price (Live)
- **Data Source**: Yahoo Finance `ticker.info` or latest history
- **Refresh**: Periodic (15min), Live (1min), On-demand
- **Storage**: `live_prices` table + `raw_market_data`

## Best Practices

1. **DRY Principle**: All data fetching goes through `DataRefreshManager`
2. **SOLID Principles**: 
   - Single Responsibility: Each strategy handles one refresh mode
   - Open/Closed: Easy to add new data sources or strategies
   - Liskov Substitution: All data sources implement `BaseDataSource`
   - Interface Segregation: Clean interfaces for each component
   - Dependency Inversion: Depend on abstractions, not concretions

3. **Rate Limiting**: Periodic and live workers limit concurrent refreshes
4. **Error Handling**: All refresh operations have try/except blocks
5. **Logging**: Comprehensive logging for debugging and monitoring
6. **Caching**: Refresh tracking prevents unnecessary API calls

## Future Enhancements

1. **Multiple Data Sources**: Add Alpha Vantage, Polygon.io, IEX Cloud
2. **Data Source Fallback**: Automatic fallback if primary source fails
3. **WebSocket Support**: Real-time price updates via WebSocket
4. **Data Quality Checks**: Validate data freshness and completeness
5. **Cost Tracking**: Monitor API usage and costs per data source
6. **Distributed Refresh**: Scale refresh operations across multiple workers

