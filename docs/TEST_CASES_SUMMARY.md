# Test Cases Summary for Portfolio & Watchlist Metrics

## Quick Reference: Test Commands

### Run All Metrics Tests
```bash
cd python-worker
python -m pytest tests/test_portfolio_watchlist_metrics.py -v
```

### Run Specific Test Categories

#### Portfolio Tests
```bash
# Test holding metrics update
python -m pytest tests/test_portfolio_watchlist_metrics.py::TestPortfolioWatchlistMetrics::test_update_holding_metrics -v

# Test portfolio performance calculation
python -m pytest tests/test_portfolio_watchlist_metrics.py::TestPortfolioWatchlistMetrics::test_calculate_portfolio_performance -v

# Test updating all holdings
python -m pytest tests/test_portfolio_watchlist_metrics.py::TestPortfolioWatchlistMetrics::test_update_all_portfolio_holdings -v

# Test calculation accuracy
python -m pytest tests/test_portfolio_watchlist_metrics.py::TestPortfolioWatchlistMetrics::test_holding_calculations_accuracy -v
```

#### Watchlist Tests
```bash
# Test watchlist item metrics update
python -m pytest tests/test_portfolio_watchlist_metrics.py::TestPortfolioWatchlistMetrics::test_update_watchlist_item_metrics -v

# Test watchlist performance calculation
python -m pytest tests/test_portfolio_watchlist_metrics.py::TestPortfolioWatchlistMetrics::test_calculate_watchlist_performance -v

# Test updating all items
python -m pytest tests/test_portfolio_watchlist_metrics.py::TestPortfolioWatchlistMetrics::test_update_all_watchlist_items -v

# Test calculation accuracy
python -m pytest tests/test_portfolio_watchlist_metrics.py::TestPortfolioWatchlistMetrics::test_watchlist_item_calculations_accuracy -v
```

### Run All Integration Tests
```bash
# All portfolio and watchlist tests
python -m pytest tests/test_watchlist_and_portfolio_integration.py tests/test_portfolio_watchlist_metrics.py -v

# With coverage
python -m pytest tests/test_portfolio_watchlist_metrics.py --cov=app.services.portfolio_calculator --cov=app.services.watchlist_calculator -v
```

## Test Coverage

### ✅ Portfolio Metrics Tests

1. **`test_update_holding_metrics`**
   - Creates holding for AAPL
   - Updates all metrics (price, value, P&L, sector, industry)
   - Verifies all fields populated correctly

2. **`test_calculate_portfolio_performance`**
   - Calculates portfolio performance snapshot
   - Verifies total value, cost basis, P&L
   - Verifies snapshot saved to database

3. **`test_update_all_portfolio_holdings`**
   - Updates multiple holdings in portfolio
   - Verifies all holdings have metrics

4. **`test_all_holding_fields_populated`**
   - Verifies all critical fields are populated
   - Checks: current_price, current_value, cost_basis, unrealized_gain_loss, sector, industry

5. **`test_holding_calculations_accuracy`**
   - Verifies mathematical accuracy
   - Tests: cost_basis, current_value, unrealized_gain_loss calculations

### ✅ Watchlist Metrics Tests

1. **`test_update_watchlist_item_metrics`**
   - Creates watchlist item for NVDA
   - Updates all metrics (price, price change, sector, earnings)
   - Verifies all fields populated correctly

2. **`test_calculate_watchlist_performance`**
   - Calculates watchlist performance snapshot
   - Verifies averages, counts, distributions
   - Verifies snapshot saved to database

3. **`test_update_all_watchlist_items`**
   - Updates multiple items in watchlist
   - Verifies all items have metrics

4. **`test_all_watchlist_item_fields_populated`**
   - Verifies all critical fields are populated
   - Checks: current_price, price_when_added, price_change, sector, earnings_date

5. **`test_watchlist_item_calculations_accuracy`**
   - Verifies mathematical accuracy
   - Tests: price_change_since_added, price_change_percent_since_added calculations

## What Gets Tested

### Data Collection
- ✅ Current price fetching from Yahoo Finance
- ✅ Fundamentals fetching (sector, industry, market cap, dividend)
- ✅ Earnings date fetching
- ✅ Market cap category calculation

### Calculations
- ✅ Holding P&L (unrealized gain/loss)
- ✅ Portfolio total value and performance
- ✅ Watchlist item price changes
- ✅ Watchlist performance metrics
- ✅ Mathematical accuracy of all calculations

### Database Updates
- ✅ All new fields populated in holdings table
- ✅ All new fields populated in watchlist_items table
- ✅ Performance snapshots saved correctly
- ✅ Timestamps updated correctly

## Expected Test Results

### Successful Test Run
```
test_update_holding_metrics ... ✅ PASSED
test_calculate_portfolio_performance ... ✅ PASSED
test_update_all_portfolio_holdings ... ✅ PASSED
test_all_holding_fields_populated ... ✅ PASSED
test_holding_calculations_accuracy ... ✅ PASSED
test_update_watchlist_item_metrics ... ✅ PASSED
test_calculate_watchlist_performance ... ✅ PASSED
test_update_all_watchlist_items ... ✅ PASSED
test_all_watchlist_item_fields_populated ... ✅ PASSED
test_watchlist_item_calculations_accuracy ... ✅ PASSED

10 passed in X.XXs
```

## Troubleshooting

### If Tests Fail

1. **Database Connection Issues**
   - Ensure database is initialized: `python -m app.database init_database`
   - Check database path in settings

2. **Data Source Issues**
   - Verify internet connection (Yahoo Finance API)
   - Check if symbols are valid (AAPL, GOOGL, NVDA, MSFT)

3. **Calculation Errors**
   - Check for division by zero
   - Verify data types (float vs int)
   - Check for NULL values

4. **Import Errors**
   - Ensure all dependencies installed: `pip install -r requirements.txt`
   - Check Python path includes project root

## Manual Verification

### Test API Endpoints

```bash
# Update portfolio metrics
curl -X POST http://localhost:8001/api/v1/portfolios/portfolio1/update-metrics

# Update holding metrics
curl -X POST http://localhost:8001/api/v1/holdings/holding1/update-metrics

# Update watchlist metrics
curl -X POST http://localhost:8001/api/v1/watchlists/watchlist1/update-metrics

# Update watchlist item metrics
curl -X POST http://localhost:8001/api/v1/watchlist-items/item1/update-metrics
```

### Verify Database

```bash
# Check holdings table
sqlite3 db/trading.db "SELECT holding_id, stock_symbol, current_price, current_value, unrealized_gain_loss, sector FROM holdings LIMIT 5;"

# Check watchlist_items table
sqlite3 db/trading.db "SELECT item_id, stock_symbol, current_price, price_change_percent_since_added, sector, earnings_date FROM watchlist_items LIMIT 5;"

# Check portfolio_performance table
sqlite3 db/trading.db "SELECT portfolio_id, snapshot_date, total_value, total_gain_loss_percent FROM portfolio_performance ORDER BY snapshot_date DESC LIMIT 5;"

# Check watchlist_performance table
sqlite3 db/trading.db "SELECT watchlist_id, snapshot_date, total_stocks, avg_price_change_percent FROM watchlist_performance ORDER BY snapshot_date DESC LIMIT 5;"
```

## Next Steps After Tests Pass

1. ✅ Verify all tests pass
2. ✅ Run batch job manually to test full pipeline
3. ✅ Test API endpoints with real data
4. ✅ Verify UI displays new fields correctly
5. ✅ Monitor batch job logs for errors

