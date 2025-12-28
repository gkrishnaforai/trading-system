# Data Source Integration Tests

## Overview

Comprehensive integration tests for data sources using **real market data** (no mocks). Tests all data fetching functionality, refresh modes, and the complete data pipeline.

## Test Files

### 1. `test_data_source_integration.py`
Tests individual data source methods with real stock data.

**Symbols Tested**: AAPL, NVDA, GOOGL, PLTR

**Test Coverage**:
- ✅ Data source availability
- ✅ Daily price data (1 year historical)
- ✅ On-demand price data (specific date ranges)
- ✅ Current/live price
- ✅ Fundamentals data
- ✅ News articles
- ✅ Earnings data
- ✅ Industry peers
- ✅ Save and retrieve from database
- ✅ Data completeness for signal calculation
- ✅ Different refresh modes (daily, on-demand, periodic)
- ✅ Data consistency
- ✅ Error handling

### 2. `test_data_refresh_integration.py`
Tests the complete data refresh pipeline with real data.

**Test Coverage**:
- ✅ Scheduled refresh mode (daily batch)
- ✅ On-demand refresh (all data types)
- ✅ Automatic indicator calculation
- ✅ Periodic refresh mode
- ✅ Data refresh tracking
- ✅ Full pipeline (fetch → save → calculate → signals)
- ✅ Error handling

## Running the Tests

### Run All Data Source Tests
```bash
cd python-worker
python -m pytest tests/test_data_source_integration.py -v
```

### Run Data Refresh Tests
```bash
cd python-worker
python -m pytest tests/test_data_refresh_integration.py -v
```

### Run Both Test Suites
```bash
cd python-worker
python -m pytest tests/test_data_source_integration.py tests/test_data_refresh_integration.py -v
```

### Run with Specific Symbol
```bash
python -m pytest tests/test_data_source_integration.py::TestDataSourceIntegration::test_fetch_daily_price_data -v -k AAPL
```

## Test Results Validation

### Expected Results

1. **Price Data**:
   - ✅ At least 200 trading days for 1 year
   - ✅ All required columns (date, open, high, low, close, volume)
   - ✅ No NaN values in critical columns
   - ✅ Valid price relationships (high >= low, etc.)

2. **Current Price**:
   - ✅ Valid numeric value
   - ✅ Positive price
   - ✅ Within 5% of latest historical close

3. **Fundamentals**:
   - ✅ Dictionary structure
   - ✅ May be empty (depends on data source)

4. **News**:
   - ✅ List of articles
   - ✅ Each article is a dictionary
   - ✅ May be empty (depends on availability)

5. **Earnings**:
   - ✅ List of earnings records
   - ✅ Each record is a dictionary
   - ✅ May be empty (depends on availability)

6. **Industry Peers**:
   - ✅ Dictionary with sector/industry/peers
   - ✅ Peers is a list
   - ✅ May be empty (depends on availability)

## Integration with Signal Calculation

The tests ensure that all data required for signal calculation is available:

1. **Price Data**: Minimum 200 days for indicators (SMA200, etc.)
2. **Current Price**: For real-time signals
3. **Fundamentals**: Optional but preferred
4. **Indicators**: Auto-calculated after price data refresh

## Data Refresh Modes Tested

### 1. Scheduled (Daily Batch)
- Fetches 1 year of historical data
- Runs automatically (e.g., 1 AM daily)
- Full data refresh

### 2. On-Demand
- Fetches specific date ranges
- Triggered by user actions
- Can refresh all data types

### 3. Periodic
- Incremental updates
- Current price updates
- Regular intervals (e.g., every 15 minutes)

### 4. Live
- Real-time price updates
- News updates
- Market hours only

## Error Handling

Tests validate that the system handles errors gracefully:
- ✅ Invalid symbols don't crash the system
- ✅ Network errors are handled
- ✅ Missing data is handled
- ✅ Database errors are caught

## Database Validation

Tests verify that data is correctly saved to the database:
- ✅ Price data in `raw_market_data` table
- ✅ Indicators in `aggregated_indicators` table
- ✅ Refresh tracking in `data_refresh_tracking` table
- ✅ Data integrity (no duplicates, valid dates)

## Performance Considerations

These tests use real API calls, so:
- ⚠️ May take several minutes to complete
- ⚠️ Rate limiting may apply
- ⚠️ Network connectivity required
- ✅ Tests are designed to be resilient to temporary failures

## Continuous Integration

For CI/CD pipelines:
- Run tests with `--maxfail=1` to stop on first failure
- Use `--tb=short` for concise output
- Consider running tests in parallel for speed
- Cache test data when possible

## Example Output

```
================================================================================
DATA SOURCE INTEGRATION TESTS - REAL MARKET DATA
================================================================================

📊 Testing with symbols: AAPL, NVDA, GOOGL, PLTR
📅 Test date: 2025-12-21 10:30:00
================================================================================

✅ AAPL: Data source available
📥 Fetching 1 year of daily price data for AAPL...
✅ AAPL: 252 rows, Date range: 2024-12-21 to 2025-12-21
   Latest close: $185.50, Volume: 45,234,567

✅ NVDA: Data source available
📥 Fetching 1 year of daily price data for NVDA...
✅ NVDA: 252 rows, Date range: 2024-12-21 to 2025-12-21
   Latest close: $485.20, Volume: 32,123,456
...
```

## Troubleshooting

### Common Issues

1. **No data returned**:
   - Check network connectivity
   - Verify data source API is available
   - Check rate limits

2. **Missing columns**:
   - Verify data source implementation
   - Check data normalization

3. **Database errors**:
   - Ensure database is initialized
   - Check database permissions
   - Verify schema is up to date

4. **Timeout errors**:
   - Increase timeout values
   - Check network latency
   - Verify API response times

## Next Steps

1. Add tests for additional data sources (Alpha Vantage, Polygon, etc.)
2. Add performance benchmarks
3. Add load testing for concurrent requests
4. Add tests for data source failover
5. Add tests for data source comparison

