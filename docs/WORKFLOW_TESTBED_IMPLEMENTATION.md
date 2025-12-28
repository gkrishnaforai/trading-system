# Workflow Engine Testbed Implementation

## Overview

**Industry Standard**: Complete workflow lifecycle testing that mirrors the production data load workflow

**Key Principle**: Each workflow stage is a test case that can be run independently or as part of end-to-end flow

---

## Workflow Engine Lifecycle

The testbed follows the complete data load workflow:

```
📥 Stage 1: Data Ingestion
   ↓
✅ Stage 2: Validation & Audit
   ↓
📊 Stage 3: Indicator Calculation
   ↓
🎯 Stage 4: Signal Generation
   ↓
🔍 Stage 5: Stock Screening
   ↓
🔄 End-to-End Workflow
```

---

## Implementation

### 1. Workflow Testbed (`streamlit-app/testbed_workflow.py`)

**Purpose**: Interactive UI for testing each workflow stage

**Features**:
- ✅ Stage-by-stage testing
- ✅ Real-time results display
- ✅ Audit trail visualization
- ✅ Indicator calculation verification
- ✅ Signal generation testing
- ✅ Stock screening with examples
- ✅ End-to-end workflow for multiple symbols

**Test Symbols**: NVDA, AAPL, ASTL, LCID, STOCKS

**Usage**:
1. Navigate to Testbed → "🔄 Workflow Engine Lifecycle"
2. Select a stage from sidebar
3. Run tests for individual symbols or end-to-end

### 2. Integration Tests (`python-worker/tests/test_workflow_integration.py`)

**Purpose**: Automated tests for complete workflow lifecycle

**Features**:
- ✅ No mocks - uses real data
- ✅ Tests all workflow stages
- ✅ Validates database operations
- ✅ Tests with multiple symbols
- ✅ End-to-end workflow validation

**Test Methods**:
- `test_stage_1_data_ingestion()` - Tests data loading
- `test_stage_2_validation_audit()` - Tests validation and audit
- `test_stage_3_indicator_calculation()` - Tests indicator calculation
- `test_stage_4_signal_generation()` - Tests signal generation
- `test_stage_5_stock_screening()` - Tests stock screening
- `test_end_to_end_workflow()` - Tests complete workflow
- `test_workflow_orchestrator()` - Tests orchestrator directly

**Run Tests**:
```bash
cd python-worker
python -m pytest tests/test_workflow_integration.py -v
```

---

## Workflow Stages Details

### Stage 1: Data Ingestion

**What it does**:
- Fetches raw price data (OHLCV) from data sources
- Validates data quality
- Saves to database with duplicate prevention
- Creates audit records

**Test Cases**:
- ✅ Data fetch success
- ✅ Database storage
- ✅ Duplicate prevention
- ✅ Audit trail creation

**Example**:
```python
result = refresh_manager.refresh_data(
    symbol='AAPL',
    data_types=[DataType.PRICE_HISTORICAL],
    mode=RefreshMode.ON_DEMAND,
    force=True
)
```

### Stage 2: Validation & Audit

**What it does**:
- Checks data quality (validation reports)
- Reviews audit history
- Checks signal readiness
- Provides actionable recommendations

**Test Cases**:
- ✅ Validation report generation
- ✅ Audit history retrieval
- ✅ Signal readiness check
- ✅ Error detection and reporting

**Example**:
```python
# Get audit history
audit = python_client.get(f"api/v1/data-fetch-audit/{symbol}")

# Get validation report
validation = python_client.get(f"api/v1/data-validation-reports/{symbol}")

# Check signal readiness
readiness = python_client.get(f"api/v1/signal-readiness/{symbol}")
```

### Stage 3: Indicator Calculation

**What it does**:
- Calculates all technical indicators from price data
- Stores indicators in database
- Validates indicator values
- Shows calculated fields

**Test Cases**:
- ✅ Indicator calculation success
- ✅ Database storage
- ✅ Indicator value validation
- ✅ Industry standard flags

**Indicators Calculated**:
- Moving Averages: EMA9, EMA21, EMA20, EMA50, SMA50, SMA200
- Momentum: RSI, MACD, MACD Signal, MACD Histogram
- Volatility: ATR, Bollinger Bands
- Flags: Price > SMA200, EMA crossovers, Volume confirmation

**Example**:
```python
success = indicator_service.calculate_indicators('AAPL')
indicators = DatabaseQueryHelper.get_latest_indicators('AAPL')
```

### Stage 4: Signal Generation

**What it does**:
- Generates buy/sell/hold signals from indicators
- Calculates confidence scores
- Provides reasoning
- Uses strategy service

**Test Cases**:
- ✅ Signal generation success
- ✅ Valid signal values (buy/sell/hold)
- ✅ Confidence score validation (0-1)
- ✅ Reason provided

**Example**:
```python
result = strategy_service.execute_strategy(
    strategy_name='technical',
    indicators=indicators,
    market_data=market_data,
    context={'symbol': 'AAPL'}
)
```

### Stage 5: Stock Screening

**What it does**:
- Screens stocks based on criteria
- Filters by price vs MAs, fundamentals, growth
- Returns matching stocks
- Shows examples

**Test Cases**:
- ✅ Screening with various criteria
- ✅ Results validation
- ✅ Multiple symbol examples

**Screening Criteria**:
- Price vs Moving Averages (below SMA50, SMA200)
- Fundamentals (good fundamentals, growth stock, exponential growth)
- RSI range
- Custom combinations

**Example**:
```python
results = screener_service.screen_stocks(
    has_good_fundamentals=True,
    price_below_sma50=True,
    limit=50
)
```

### End-to-End Workflow

**What it does**:
- Runs all stages sequentially for multiple symbols
- Validates each stage
- Shows complete results
- Provides summary

**Test Cases**:
- ✅ All stages complete successfully
- ✅ Data flows correctly between stages
- ✅ Error handling
- ✅ Performance metrics

**Example**:
```python
result = eod_workflow.execute_daily_eod_workflow(['NVDA', 'AAPL', 'ASTL', 'LCID', 'STOCKS'])
```

---

## Integration with Existing Testbed

The workflow testbed is integrated into the main testbed:

1. **Navigation**: Testbed → "🔄 Workflow Engine Lifecycle"
2. **Integration**: Uses `importlib` to load `testbed_workflow.py`
3. **Seamless**: Works alongside existing testbed sections

---

## Test Execution

### Streamlit Testbed (Interactive)

1. Start Streamlit:
   ```bash
   cd streamlit-app
   streamlit run app.py
   ```

2. Navigate to Testbed page

3. Select "🔄 Workflow Engine Lifecycle"

4. Choose a stage and run tests

### Python Integration Tests (Automated)

```bash
cd python-worker
python -m pytest tests/test_workflow_integration.py -v
```

**Expected Output**:
```
📥 Testing Stage 1: Data Ingestion...
  ✅ NVDA: 252 rows ingested
  ✅ AAPL: 252 rows ingested
  ...

✅ Testing Stage 2: Validation & Audit...
  ✅ NVDA: Audit record found
  ...

📊 Testing Stage 3: Indicator Calculation...
  ✅ NVDA: Indicators calculated successfully
  ...

🎯 Testing Stage 4: Signal Generation...
  ✅ NVDA: Signal generated - BUY (confidence: 0.75)
  ...

🔍 Testing Stage 5: Stock Screening...
  ✅ Found 15 stocks matching criteria
  ...

🔄 Testing End-to-End Workflow...
  ✅ Stage 1: 5 symbols loaded
  ✅ Stage 3: 5 indicators calculated
  ✅ Stage 4: 5 signals generated
  ✅ End-to-End Workflow completed successfully!
```

---

## Key Features

### ✅ Real Data (No Mocks)

- Uses actual API calls
- Real database operations
- Real market data (NVDA, AAPL, ASTL, LCID, STOCKS)
- Industry-standard validation

### ✅ Complete Workflow

- All stages tested
- Data flows correctly
- Error handling validated
- Performance tracked

### ✅ Audit Trail

- Every operation audited
- Validation reports generated
- Signal readiness checked
- Actionable recommendations

### ✅ Industry Standards

- Follows EOD workflow
- Uses workflow orchestrator
- Fail-fast gates
- Duplicate prevention

---

## Example Test Scenarios

### Scenario 1: Single Symbol Workflow

1. Select "📥 Stage 1: Data Ingestion"
2. Choose symbol: NVDA
3. Click "🚀 Run Data Ingestion"
4. View results and audit

5. Select "✅ Stage 2: Validation & Audit"
6. View validation report and readiness

7. Select "📊 Stage 3: Indicator Calculation"
8. View calculated indicators

9. Select "🎯 Stage 4: Signal Generation"
10. View buy/sell/hold signal

### Scenario 2: End-to-End for All Symbols

1. Select "🔄 End-to-End Workflow"
2. Select all symbols: NVDA, AAPL, ASTL, LCID, STOCKS
3. Click "🚀 Run End-to-End Workflow"
4. View complete results for each symbol

### Scenario 3: Stock Screening

1. Select "🔍 Stage 5: Stock Screening"
2. Set criteria:
   - Price Below SMA50: ✅
   - Good Fundamentals: ✅
   - RSI: 30-70
3. Click "🔍 Run Screener"
4. View matching stocks

---

## Summary

✅ **Complete**: All workflow stages tested
✅ **Real Data**: No mocks, uses actual APIs and database
✅ **Interactive**: Streamlit UI for manual testing
✅ **Automated**: Python tests for CI/CD
✅ **Industry Standard**: Follows EOD workflow lifecycle
✅ **Examples**: NVDA, AAPL, ASTL, LCID, STOCKS

The testbed now provides comprehensive testing of the complete workflow engine lifecycle, from data ingestion to signal generation and screening, with full audit trails and validation.

