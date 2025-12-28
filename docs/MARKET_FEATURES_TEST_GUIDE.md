# Market Features Test Guide

## Overview

Comprehensive integration tests for all market features (Market Movers, Sector Performance, Stock Comparison, Analyst Ratings, Market Overview, Market Trends).

## Test File

**Location**: `python-worker/tests/test_market_features_integration.py`

## Test Cases

### 1. Market Movers Tests

#### `test_calculate_market_movers`
- Creates live price data for test symbols
- Calculates market movers (gainers, losers, most_active)
- Verifies structure and data

#### `test_get_market_movers`
- Retrieves market movers from database
- Tests all mover types (gainers, losers, most_active)
- Verifies data structure

**Run:**
```bash
python -m pytest tests/test_market_features_integration.py::TestMarketFeaturesIntegration::test_calculate_market_movers -v
python -m pytest tests/test_market_features_integration.py::TestMarketFeaturesIntegration::test_get_market_movers -v
```

### 2. Sector Performance Tests

#### `test_calculate_sector_performance`
- Creates portfolio with holdings
- Updates holdings to populate sectors
- Calculates sector performance
- Verifies structure and metrics

#### `test_get_sector_performance`
- Retrieves sector performance from database
- Verifies data structure

**Run:**
```bash
python -m pytest tests/test_market_features_integration.py::TestMarketFeaturesIntegration::test_calculate_sector_performance -v
python -m pytest tests/test_market_features_integration.py::TestMarketFeaturesIntegration::test_get_sector_performance -v
```

### 3. Stock Comparison Tests

#### `test_compare_stocks`
- Compares multiple stocks (AAPL, GOOGL, NVDA)
- Verifies comparison data structure
- Checks all symbols have data

#### `test_compare_stocks_validation`
- Tests empty list validation
- Tests too many symbols validation (max 10)

**Run:**
```bash
python -m pytest tests/test_market_features_integration.py::TestMarketFeaturesIntegration::test_compare_stocks -v
python -m pytest tests/test_market_features_integration.py::TestMarketFeaturesIntegration::test_compare_stocks_validation -v
```

### 4. Analyst Ratings Tests

#### `test_fetch_analyst_ratings`
- Fetches analyst ratings from Finnhub API (if configured)
- Saves to database
- Verifies ratings and consensus

**Note**: Requires `FINNHUB_API_KEY` environment variable. If not set, test will skip gracefully.

#### `test_get_analyst_ratings`
- Retrieves analyst ratings from database
- Verifies structure

**Run:**
```bash
# With API key
FINNHUB_API_KEY=your_key python -m pytest tests/test_market_features_integration.py::TestMarketFeaturesIntegration::test_fetch_analyst_ratings -v

# Without API key (will skip)
python -m pytest tests/test_market_features_integration.py::TestMarketFeaturesIntegration::test_fetch_analyst_ratings -v
```

### 5. Market Overview Tests

#### `test_get_market_overview`
- Gets comprehensive market overview
- Verifies market status, indices, statistics
- Checks structure

**Run:**
```bash
python -m pytest tests/test_market_features_integration.py::TestMarketFeaturesIntegration::test_get_market_overview -v
```

### 6. Market Trends Tests

#### `test_calculate_market_trends`
- Calculates market trends (sectors, industries, market cap)
- Verifies structure and overall trend

#### `test_get_market_trends`
- Retrieves market trends from database
- Tests filtering by trend_type

**Run:**
```bash
python -m pytest tests/test_market_features_integration.py::TestMarketFeaturesIntegration::test_calculate_market_trends -v
python -m pytest tests/test_market_features_integration.py::TestMarketFeaturesIntegration::test_get_market_trends -v
```

### 7. Integration Workflow Test

#### `test_full_market_features_workflow`
- Tests complete workflow of all features
- Verifies end-to-end integration

**Run:**
```bash
python -m pytest tests/test_market_features_integration.py::TestMarketFeaturesIntegration::test_full_market_features_workflow -v
```

## Running All Tests

```bash
# Run all market features tests
cd python-worker
python -m pytest tests/test_market_features_integration.py -v

# Run with coverage
python -m pytest tests/test_market_features_integration.py --cov=app.services.market_movers_service --cov=app.services.sector_performance_service --cov=app.services.stock_comparison_service --cov=app.services.analyst_ratings_service --cov=app.services.market_overview_service --cov=app.services.market_trends_service -v

# Run with network access (for real API calls)
python -m pytest tests/test_market_features_integration.py -v --network
```

## Test Data

Tests use real stock symbols:
- AAPL (Apple)
- GOOGL (Google)
- NVDA (NVIDIA)
- MSFT (Microsoft)
- TSLA (Tesla)

## Expected Results

### Successful Test Run
```
test_calculate_market_movers ... ✅ PASSED
test_get_market_movers ... ✅ PASSED
test_calculate_sector_performance ... ✅ PASSED
test_get_sector_performance ... ✅ PASSED
test_compare_stocks ... ✅ PASSED
test_compare_stocks_validation ... ✅ PASSED
test_fetch_analyst_ratings ... ✅ PASSED (or SKIPPED if no API key)
test_get_analyst_ratings ... ✅ PASSED
test_get_market_overview ... ✅ PASSED
test_calculate_market_trends ... ✅ PASSED
test_get_market_trends ... ✅ PASSED
test_full_market_features_workflow ... ✅ PASSED

11-12 passed in X.XXs
```

## Troubleshooting

### No Live Price Data
- Ensure live prices are being saved
- Run: `curl -X POST http://localhost:8001/api/v1/refresh-live-price/AAPL`

### No Sector Data
- Ensure holdings/watchlists have sectors populated
- Run portfolio calculator: `curl -X POST http://localhost:8001/api/v1/portfolios/{portfolio_id}/update-metrics`

### Analyst Ratings Not Working
- Check `FINNHUB_API_KEY` is set
- Verify API key is valid
- Check API rate limits

### Database Errors
- Ensure migration 007 is applied
- Run: `./db/scripts/init_db.sh`

## API Testing

### Test Market Movers API
```bash
# Get gainers
curl "http://localhost:8001/api/v1/market/movers?mover_type=gainers&period=day&limit=10"

# Calculate movers
curl -X POST "http://localhost:8001/api/v1/market/movers/calculate?period=day&limit=20"
```

### Test Sector Performance API
```bash
# Get all sectors
curl "http://localhost:8001/api/v1/market/sectors"

# Calculate performance
curl -X POST "http://localhost:8001/api/v1/market/sectors/calculate"
```

### Test Stock Comparison API
```bash
curl -X POST http://localhost:8001/api/v1/stocks/compare \
  -H "Content-Type: application/json" \
  -d '{"symbols": ["AAPL", "GOOGL", "NVDA"]}'
```

### Test Analyst Ratings API
```bash
# Get ratings
curl "http://localhost:8001/api/v1/stock/AAPL/analyst-ratings"

# Fetch ratings (requires FINNHUB_API_KEY)
curl -X POST "http://localhost:8001/api/v1/stock/AAPL/analyst-ratings/fetch"
```

### Test Market Overview API
```bash
curl "http://localhost:8001/api/v1/market/overview"
```

### Test Market Trends API
```bash
# Get all trends
curl "http://localhost:8001/api/v1/market/trends"

# Get sector trends
curl "http://localhost:8001/api/v1/market/trends?trend_type=sector"

# Calculate trends
curl -X POST "http://localhost:8001/api/v1/market/trends/calculate"
```

## Summary

✅ **11 test cases** covering all market features
✅ **Real data** (no mocks)
✅ **Fail-fast** error handling
✅ **Comprehensive validation**
✅ **Integration workflow** test

All tests follow DRY, SOLID principles and use existing system architecture.

