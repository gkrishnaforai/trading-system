# Swing Trading Test Commands

## Overview

All tests use **real data only** (no mocks). Tests fetch actual market data from data sources and validate against real market conditions.

## Prerequisites

1. **Database initialized**: Run migrations to create swing trading tables
2. **Data source available**: Yahoo Finance or other data source configured
3. **Network access**: Required to fetch real market data

## Test Files

1. `test_swing_indicators.py` - Unit tests for swing indicators
2. `test_multi_timeframe_service.py` - Unit tests for multi-timeframe service
3. `test_swing_trend_strategy.py` - Unit tests for swing trend strategy
4. `test_swing_risk_manager.py` - Unit tests for swing risk manager
5. `test_swing_trading_integration.py` - Integration tests for end-to-end workflow

## Running Tests

### Run All Swing Trading Tests

```bash
cd python-worker
python -m pytest tests/test_swing_*.py -v
```

### Run Specific Test File

```bash
# Swing indicators
python -m pytest tests/test_swing_indicators.py -v

# Multi-timeframe service
python -m pytest tests/test_multi_timeframe_service.py -v

# Swing trend strategy
python -m pytest tests/test_swing_trend_strategy.py -v

# Swing risk manager
python -m pytest tests/test_swing_risk_manager.py -v

# Integration tests
python -m pytest tests/test_swing_trading_integration.py -v
```

### Run Specific Test Class

```bash
# Test ADX calculation
python -m pytest tests/test_swing_indicators.py::TestSwingIndicators::test_adx_calculation -v

# Test signal generation
python -m pytest tests/test_swing_trend_strategy.py::TestSwingTrendStrategy::test_signal_generation -v

# Test position sizing
python -m pytest tests/test_swing_risk_manager.py::TestSwingRiskManager::test_position_sizing -v

# Test end-to-end workflow
python -m pytest tests/test_swing_trading_integration.py::TestSwingTradingIntegration::test_end_to_end_swing_trading -v
```

### Run with Output

```bash
# Show print statements
python -m pytest tests/test_swing_*.py -v -s

# Show detailed output
python -m pytest tests/test_swing_*.py -vv
```

### Run with Coverage

```bash
# Install coverage if not installed
pip install pytest-cov

# Run with coverage
python -m pytest tests/test_swing_*.py --cov=app.indicators.swing --cov=app.services.multi_timeframe_service --cov=app.strategies.swing --cov=app.services.swing_risk_manager --cov-report=html
```

## Quick Test Commands

### All Swing Tests (Recommended)

```bash
cd /Users/krishnag/tools/trading-system/python-worker && python -m pytest tests/test_swing_*.py -v -s
```

### Individual Test Files

```bash
# Indicators
cd /Users/krishnag/tools/trading-system/python-worker && python -m pytest tests/test_swing_indicators.py -v -s

# Multi-timeframe
cd /Users/krishnag/tools/trading-system/python-worker && python -m pytest tests/test_multi_timeframe_service.py -v -s

# Strategy
cd /Users/krishnag/tools/trading-system/python-worker && python -m pytest tests/test_swing_trend_strategy.py -v -s

# Risk Manager
cd /Users/krishnag/tools/trading-system/python-worker && python -m pytest tests/test_swing_risk_manager.py -v -s

# Integration
cd /Users/krishnag/tools/trading-system/python-worker && python -m pytest tests/test_swing_trading_integration.py -v -s
```

## Expected Test Results

### ✅ Successful Test Run

```
test_swing_indicators.py::TestSwingIndicators::test_adx_calculation ... ✅ PASSED
test_swing_indicators.py::TestSwingIndicators::test_stochastic_calculation ... ✅ PASSED
test_swing_indicators.py::TestSwingIndicators::test_williams_r_calculation ... ✅ PASSED
test_swing_indicators.py::TestSwingIndicators::test_vwap_calculation ... ✅ PASSED
test_swing_indicators.py::TestSwingIndicators::test_fibonacci_retracements ... ✅ PASSED

test_multi_timeframe_service.py::TestMultiTimeframeService::test_fetch_and_save_daily ... ✅ PASSED
test_multi_timeframe_service.py::TestMultiTimeframeService::test_fetch_and_save_weekly ... ✅ PASSED
test_multi_timeframe_service.py::TestMultiTimeframeService::test_get_timeframe_data ... ✅ PASSED

test_swing_trend_strategy.py::TestSwingTrendStrategy::test_signal_generation ... ✅ PASSED
test_swing_trend_strategy.py::TestSwingTrendStrategy::test_entry_conditions ... ✅ PASSED

test_swing_risk_manager.py::TestSwingRiskManager::test_position_sizing ... ✅ PASSED
test_swing_risk_manager.py::TestSwingRiskManager::test_portfolio_heat ... ✅ PASSED

test_swing_trading_integration.py::TestSwingTradingIntegration::test_end_to_end_swing_trading ... ✅ PASSED
test_swing_trading_integration.py::TestSwingTradingIntegration::test_multi_symbol_analysis ... ✅ PASSED

X passed in Y.XXs
```

## Test Data

Tests use real market data for:
- **AAPL** (Apple)
- **GOOGL** (Google)
- **NVDA** (NVIDIA)
- **TQQQ** (Triple-leveraged QQQ ETF)

## Troubleshooting

### No Data Available

If tests fail with "No data available":
1. Check network connection
2. Verify data source is configured
3. Check if symbols are valid
4. Try running data refresh first:
   ```bash
   curl -X POST http://localhost:8001/api/v1/refresh-data \
     -H "Content-Type: application/json" \
     -d '{"symbol": "AAPL", "data_types": ["price_historical"]}'
   ```

### Database Errors

If tests fail with database errors:
1. Ensure database is initialized:
   ```bash
   python -c "from app.database import init_database; init_database()"
   ```
2. Check migration 009 is applied:
   ```bash
   sqlite3 db/trading.db ".tables" | grep swing
   ```

### Import Errors

If tests fail with import errors:
1. Ensure you're in the `python-worker` directory
2. Check Python path:
   ```bash
   python -c "import sys; print(sys.path)"
   ```

## Test Coverage

- ✅ **Swing Indicators**: ADX, Stochastic, Williams %R, VWAP, Fibonacci
- ✅ **Multi-Timeframe Service**: Data fetching, aggregation, persistence
- ✅ **Swing Trend Strategy**: Signal generation, entry/exit conditions
- ✅ **Swing Risk Manager**: Position sizing, portfolio heat
- ✅ **Integration**: End-to-end workflow, multi-symbol analysis

---

**Note**: All tests use real data and may take longer to run due to network requests for market data.
