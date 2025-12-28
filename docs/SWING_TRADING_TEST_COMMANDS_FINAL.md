# Swing Trading Test Commands - Final

## Quick Start

### Run All Swing Trading Tests

```bash
cd /Users/krishnag/tools/trading-system/python-worker
python -m pytest tests/test_swing_*.py -v -s
```

## Test Files

1. **test_swing_indicators.py** - ADX, Stochastic, Williams %R, VWAP, Fibonacci
2. **test_multi_timeframe_service.py** - Multi-timeframe data service
3. **test_swing_trend_strategy.py** - Swing trend strategy
4. **test_swing_risk_manager.py** - Risk management
5. **test_swing_trading_integration.py** - End-to-end integration

## Commands

### All Tests

```bash
cd /Users/krishnag/tools/trading-system/python-worker
python -m pytest tests/test_swing_*.py -v -s
```

### Individual Test Files

```bash
# Indicators
cd /Users/krishnag/tools/trading-system/python-worker
python -m pytest tests/test_swing_indicators.py -v -s

# Multi-timeframe
cd /Users/krishnag/tools/trading-system/python-worker
python -m pytest tests/test_multi_timeframe_service.py -v -s

# Strategy
cd /Users/krishnag/tools/trading-system/python-worker
python -m pytest tests/test_swing_trend_strategy.py -v -s

# Risk Manager
cd /Users/krishnag/tools/trading-system/python-worker
python -m pytest tests/test_swing_risk_manager.py -v -s

# Integration
cd /Users/krishnag/tools/trading-system/python-worker
python -m pytest tests/test_swing_trading_integration.py -v -s
```

### Specific Tests

```bash
# Test ADX
cd /Users/krishnag/tools/trading-system/python-worker
python -m pytest tests/test_swing_indicators.py::TestSwingIndicators::test_adx_calculation -v -s

# Test signal generation
cd /Users/krishnag/tools/trading-system/python-worker
python -m pytest tests/test_swing_trend_strategy.py::TestSwingTrendStrategy::test_signal_generation -v -s

# Test end-to-end
cd /Users/krishnag/tools/trading-system/python-worker
python -m pytest tests/test_swing_trading_integration.py::TestSwingTradingIntegration::test_end_to_end_swing_trading -v -s
```

## Test Data

All tests use **real market data** for:
- AAPL (Apple)
- GOOGL (Google)  
- NVDA (NVIDIA)
- TQQQ (Triple-leveraged QQQ ETF)

## Expected Results

All tests should pass with real data. Tests will:
- Fetch actual market data
- Calculate indicators
- Generate signals
- Validate risk management
- Test end-to-end workflow

---

**Note**: Tests require network access to fetch real market data.

