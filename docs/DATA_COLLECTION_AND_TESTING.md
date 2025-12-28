# Data Collection and Testing Guide

## Overview

This document outlines how all new portfolio and watchlist fields are populated, what data sources are used, and comprehensive test cases to verify everything works.

## Data Collection Strategy

### Portfolio & Holdings Fields

#### Fields Populated from Data Sources

| Field                 | Data Source   | Method                                            | Update Frequency      |
| --------------------- | ------------- | ------------------------------------------------- | --------------------- |
| `current_price`       | Yahoo Finance | `fetch_current_price()`                           | Real-time / On-demand |
| `sector`              | Yahoo Finance | `fetch_fundamentals()` → `sector`                 | Daily batch           |
| `industry`            | Yahoo Finance | `fetch_fundamentals()` → `industry`               | Daily batch           |
| `market_cap_category` | Yahoo Finance | `fetch_fundamentals()` → `marketCap` (calculated) | Daily batch           |
| `dividend_yield`      | Yahoo Finance | `fetch_fundamentals()` → `dividendYield`          | Daily batch           |

#### Fields Calculated from Holdings

| Field                          | Calculation                                 | Service                      |
| ------------------------------ | ------------------------------------------- | ---------------------------- |
| `current_value`                | `quantity * current_price`                  | `PortfolioCalculatorService` |
| `cost_basis`                   | `quantity * avg_entry_price`                | `PortfolioCalculatorService` |
| `unrealized_gain_loss`         | `current_value - cost_basis`                | `PortfolioCalculatorService` |
| `unrealized_gain_loss_percent` | `(unrealized_gain_loss / cost_basis) * 100` | `PortfolioCalculatorService` |
| `allocation_percent`           | `(current_value / portfolio_total) * 100`   | `PortfolioCalculatorService` |

#### Fields Set by User/System

| Field                | Source                     | Notes               |
| -------------------- | -------------------------- | ------------------- |
| `target_price`       | User input                 | Entry/exit strategy |
| `stop_loss_price`    | User input / Calculated    | Risk management     |
| `take_profit_price`  | User input / Calculated    | Profit taking       |
| `realized_gain_loss` | System (on position close) | Tax reporting       |
| `exit_price`         | System (on position close) | Position lifecycle  |
| `exit_date`          | System (on position close) | Position lifecycle  |
| `is_closed`          | System (on position close) | Position lifecycle  |
| `closed_reason`      | User input                 | Analysis            |

### Watchlist & Watchlist Items Fields

#### Fields Populated from Data Sources

| Field                 | Data Source     | Method                                            | Update Frequency      |
| --------------------- | --------------- | ------------------------------------------------- | --------------------- |
| `current_price`       | Yahoo Finance   | `fetch_current_price()`                           | Real-time / On-demand |
| `price_when_added`    | System (on add) | Set when item added                               | One-time              |
| `sector`              | Yahoo Finance   | `fetch_fundamentals()` → `sector`                 | Daily batch           |
| `industry`            | Yahoo Finance   | `fetch_fundamentals()` → `industry`               | Daily batch           |
| `market_cap_category` | Yahoo Finance   | `fetch_fundamentals()` → `marketCap` (calculated) | Daily batch           |
| `dividend_yield`      | Yahoo Finance   | `fetch_fundamentals()` → `dividendYield`          | Daily batch           |
| `earnings_date`       | Yahoo Finance   | `fetch_earnings()` → next future date             | Daily batch           |

#### Fields Calculated

| Field                              | Calculation                               | Service                      |
| ---------------------------------- | ----------------------------------------- | ---------------------------- |
| `price_change_since_added`         | `current_price - price_when_added`        | `WatchlistCalculatorService` |
| `price_change_percent_since_added` | `(price_change / price_when_added) * 100` | `WatchlistCalculatorService` |

#### Fields Set by User

| Field                  | Source                    | Notes             |
| ---------------------- | ------------------------- | ----------------- |
| `target_price`         | User input                | Entry strategy    |
| `target_date`          | User input                | Entry timing      |
| `watch_reason`         | User input                | Analysis notes    |
| `analyst_rating`       | User input / External API | Analyst consensus |
| `analyst_price_target` | User input / External API | Price target      |

### Portfolio Performance Snapshot

**Fields Calculated:**

- `total_value`: Sum of all holding `current_value`
- `cost_basis`: Sum of all holding `cost_basis`
- `total_gain_loss`: `total_value - cost_basis`
- `total_gain_loss_percent`: `(total_gain_loss / cost_basis) * 100`
- `sector_allocation`: JSON aggregation by sector
- `top_holdings`: Top 10 by value (JSON)

**Update Frequency:** Daily (batch job)

### Watchlist Performance Snapshot

**Fields Calculated:**

- `total_stocks`: Count of items
- `avg_price_change`: Average of `price_change_since_added`
- `avg_price_change_percent`: Average of `price_change_percent_since_added`
- `bullish_count`: Items with >5% gain
- `bearish_count`: Items with <-5% loss
- `neutral_count`: Remaining items
- `sector_distribution`: Count by sector (JSON)
- `top_gainers`: Top 5 gainers (JSON)
- `top_losers`: Top 5 losers (JSON)

**Update Frequency:** Daily (batch job)

## Services Created

### 1. PortfolioCalculatorService

**Location:** `python-worker/app/services/portfolio_calculator.py`

**Methods:**

- `update_holding_metrics(holding_id)` - Update single holding
- `update_portfolio_holdings(portfolio_id)` - Update all holdings in portfolio
- `calculate_portfolio_performance(portfolio_id)` - Calculate performance snapshot

**Data Sources Used:**

- `data_source.fetch_current_price()` - Current price
- `data_source.fetch_fundamentals()` - Sector, industry, market cap, dividend yield

### 2. WatchlistCalculatorService

**Location:** `python-worker/app/services/watchlist_calculator.py`

**Methods:**

- `update_watchlist_item_metrics(item_id)` - Update single item
- `update_watchlist_items(watchlist_id)` - Update all items in watchlist
- `calculate_watchlist_performance(watchlist_id)` - Calculate performance snapshot

**Data Sources Used:**

- `data_source.fetch_current_price()` - Current price
- `data_source.fetch_fundamentals()` - Sector, industry, market cap, dividend yield
- `data_source.fetch_earnings()` - Next earnings date

## Batch Job Integration

**Updated:** `python-worker/app/workers/batch_worker.py`

**New Steps Added:**

- Step 6: Update portfolio and holding metrics
- Step 7: Update watchlist item metrics

**Execution:**

- Runs automatically in nightly batch job
- Updates all portfolios and watchlists
- Calculates performance snapshots

## API Endpoints

### Portfolio Metrics

- `POST /api/v1/portfolios/{portfolio_id}/update-metrics` - Update portfolio metrics
- `POST /api/v1/holdings/{holding_id}/update-metrics` - Update single holding

### Watchlist Metrics

- `POST /api/v1/watchlists/{watchlist_id}/update-metrics` - Update watchlist metrics
- `POST /api/v1/watchlist-items/{item_id}/update-metrics` - Update single item

## Test Cases

### Test File: `test_portfolio_watchlist_metrics.py`

#### Portfolio Metrics Tests

1. **`test_update_holding_metrics`**

   - Creates holding for AAPL
   - Updates metrics
   - Verifies: current_price, current_value, cost_basis, unrealized_gain_loss, sector, industry

2. **`test_calculate_portfolio_performance`**

   - Calculates portfolio performance
   - Verifies: total_value, cost_basis, total_gain_loss, snapshot saved

3. **`test_update_all_portfolio_holdings`**

   - Updates multiple holdings
   - Verifies: All holdings have metrics

4. **`test_all_holding_fields_populated`**

   - Verifies all critical fields are populated

5. **`test_holding_calculations_accuracy`**
   - Verifies mathematical accuracy of calculations

#### Watchlist Metrics Tests

1. **`test_update_watchlist_item_metrics`**

   - Creates watchlist item for NVDA
   - Updates metrics
   - Verifies: current_price, price_when_added, price_change, sector, earnings_date

2. **`test_calculate_watchlist_performance`**

   - Calculates watchlist performance
   - Verifies: total_stocks, avg_price_change, snapshot saved

3. **`test_update_all_watchlist_items`**

   - Updates multiple items
   - Verifies: All items have metrics

4. **`test_all_watchlist_item_fields_populated`**

   - Verifies all critical fields are populated

5. **`test_watchlist_item_calculations_accuracy`**
   - Verifies mathematical accuracy of calculations

## Running Tests

### Run All Metrics Tests

```bash
cd python-worker
python -m pytest tests/test_portfolio_watchlist_metrics.py -v
```

### Run Specific Test

```bash
python -m pytest tests/test_portfolio_watchlist_metrics.py::TestPortfolioWatchlistMetrics::test_update_holding_metrics -v
```

### Run All Integration Tests

```bash
python -m pytest tests/test_watchlist_and_portfolio_integration.py tests/test_portfolio_watchlist_metrics.py -v
```

## Data Flow

### Holding Metrics Update Flow

```
1. User creates holding (via API)
   ↓
2. Batch job runs (nightly) OR On-demand API call
   ↓
3. PortfolioCalculatorService.update_holding_metrics()
   ↓
4. Fetch current_price from Yahoo Finance
   ↓
5. Fetch fundamentals (sector, industry, market cap, dividend)
   ↓
6. Calculate: current_value, cost_basis, unrealized_gain_loss, allocation_percent
   ↓
7. Update database
   ↓
8. Calculate portfolio performance snapshot
```

### Watchlist Item Metrics Update Flow

```
1. User adds item to watchlist (via API)
   ↓
2. Set price_when_added = current_price
   ↓
3. Batch job runs (nightly) OR On-demand API call
   ↓
4. WatchlistCalculatorService.update_watchlist_item_metrics()
   ↓
5. Fetch current_price from Yahoo Finance
   ↓
6. Fetch fundamentals (sector, industry, market cap, dividend)
   ↓
7. Fetch earnings (next earnings date)
   ↓
8. Calculate: price_change_since_added, price_change_percent_since_added
   ↓
9. Update database
   ↓
10. Calculate watchlist performance snapshot
```

## Missing Data Handling

### Current Price Not Available

- Logs warning
- Returns False (doesn't update)
- Retries in next batch run

### Fundamentals Not Available

- Sets sector/industry to NULL
- Continues with other calculations
- Logs warning

### Earnings Date Not Available

- Sets earnings_date to NULL
- Continues with other calculations
- Logs debug message

## Verification Checklist

### ✅ Data Sources

- [x] Current price fetching (Yahoo Finance)
- [x] Fundamentals fetching (sector, industry, market cap, dividend)
- [x] Earnings date fetching

### ✅ Calculations

- [x] Holding P&L calculations
- [x] Portfolio performance calculations
- [x] Watchlist item price change calculations
- [x] Watchlist performance calculations
- [x] Market cap category determination

### ✅ Services

- [x] PortfolioCalculatorService created
- [x] WatchlistCalculatorService created
- [x] Batch worker integration
- [x] API endpoints added

### ✅ Tests

- [x] Holding metrics update test
- [x] Portfolio performance calculation test
- [x] Watchlist item metrics update test
- [x] Watchlist performance calculation test
- [x] Calculation accuracy tests
- [x] Field population tests

## Next Steps

1. **Run Tests**: Execute all test cases to verify functionality
2. **Manual Verification**: Test with real stocks (AAPL, GOOGL, NVDA)
3. **Batch Job**: Verify nightly batch job updates all metrics
4. **API Testing**: Test API endpoints with curl/Postman
5. **UI Integration**: Add UI to display new fields in Streamlit

## Test Commands Summary

```bash
# Run all metrics tests
cd python-worker
python -m pytest tests/test_portfolio_watchlist_metrics.py -v

# Run specific test
python -m pytest tests/test_portfolio_watchlist_metrics.py::TestPortfolioWatchlistMetrics::test_update_holding_metrics -v

# Run all integration tests
python -m pytest tests/test_watchlist_and_portfolio_integration.py tests/test_portfolio_watchlist_metrics.py -v

# Run with coverage
python -m pytest tests/test_portfolio_watchlist_metrics.py --cov=app.services.portfolio_calculator --cov=app.services.watchlist_calculator -v
```
