# New Workflow Stages Implementation

## Overview

Three new workflow stages have been added to support comprehensive financial data, weekly aggregation, and growth calculations for trading decisions.

## New Workflow Stages

### Stage 2.5: Financial Data Ingestion

**Purpose**: Fetch and save comprehensive financial statements from Massive.com

**Operations**:
1. Income Statements → `income_statements` table
2. Balance Sheets → `balance_sheets` table
3. Cash Flow Statements → `cash_flow_statements` table
4. Financial Ratios → `financial_ratios` table (calculated from statements)

**Implementation**:
- `_refresh_income_statements()` - Saves income statements
- `_refresh_balance_sheets()` - Saves balance sheets
- `_refresh_cash_flow_statements()` - Saves cash flow statements
- `_refresh_financial_ratios()` - Placeholder for future ratio fetching

**Data Source**: `massive_source.fetch_comprehensive_financials()`

**Dependencies**: Runs after `ingestion` stage (needs price data)

**Status**: ✅ Implemented

### Stage 2.6: Weekly Data Aggregation

**Purpose**: Aggregate daily price data to weekly timeframe for swing trading trend confirmation

**Operations**:
1. Resample daily OHLCV data to weekly bars
2. Save to `multi_timeframe_data` table with `timeframe='weekly'`

**Implementation**:
- `DataAggregationService.aggregate_to_weekly()` - Resamples daily data to weekly
- Uses pandas `resample('W')` to aggregate:
  - Open: First open of the week
  - High: Maximum high of the week
  - Low: Minimum low of the week
  - Close: Last close of the week
  - Volume: Sum of volume for the week

**Dependencies**: Runs after `indicators` stage (needs daily price data)

**Status**: ✅ Implemented

### Stage 2.7: Growth Calculations

**Purpose**: Calculate YoY growth metrics from financial statements for screener flags and trading decisions

**Operations**:
1. Fetch income statements from database
2. Calculate revenue growth (YoY)
3. Calculate earnings growth (YoY)
4. Calculate EPS growth (YoY)
5. Update `enhanced_fundamentals` table with growth metrics

**Implementation**:
- `GrowthCalculationService.calculate_growth_metrics()` - Calculates growth from income statements
- Compares current period vs same period previous year:
  - Quarterly: Q1 2024 vs Q1 2023
  - Annual: FY 2023 vs FY 2022
- Updates `enhanced_fundamentals` table with:
  - `revenue_growth` (percentage)
  - `earnings_growth` (percentage)
  - `eps_growth` (percentage)

**Dependencies**: Runs after `financial_data` stage (needs income statements)

**Status**: ✅ Implemented

## Updated Workflow Flow

```
1. Ingestion (Price Data)
   ↓
2. Indicators (Technical Indicators)
   ↓
2.5. Financial Data (Income Statements, Balance Sheets, Cash Flow) [NEW]
   ↓
2.6. Weekly Aggregation (Daily → Weekly) [NEW]
   ↓
2.7. Growth Calculations (YoY Growth Metrics) [NEW]
   ↓
3. Signals (Trading Signals)
```

## New Data Types

Added to `DataType` enum in `refresh_strategy.py`:

```python
INCOME_STATEMENTS = "income_statements"
BALANCE_SHEETS = "balance_sheets"
CASH_FLOW_STATEMENTS = "cash_flow_statements"
FINANCIAL_RATIOS = "financial_ratios"
WEEKLY_AGGREGATION = "weekly_aggregation"
GROWTH_CALCULATIONS = "growth_calculations"
```

## New Services

### DataAggregationService (`services/data_aggregation_service.py`)

**Methods**:
- `aggregate_to_weekly(symbol, force=False)` - Aggregate daily to weekly
- `aggregate_to_monthly(symbol, force=False)` - Aggregate daily to monthly
- `aggregate_symbol(symbol, timeframes, force=False)` - Aggregate to multiple timeframes

**Features**:
- Duplicate prevention (checks if data exists)
- Handles missing data gracefully
- Returns detailed results with date ranges

### GrowthCalculationService (`services/growth_calculation_service.py`)

**Methods**:
- `calculate_growth_metrics(symbol, force=False)` - Calculate YoY growth
- `calculate_all_symbols(symbols, force=False)` - Batch calculation

**Features**:
- Compares quarterly vs quarterly, annual vs annual
- Updates `enhanced_fundamentals` table
- Handles missing data gracefully

## Database Tables Updated

### Enhanced Fundamentals Table

Now populated with:
- Growth metrics: `revenue_growth`, `earnings_growth`, `eps_growth`
- All valuation, profitability, efficiency, leverage, liquidity ratios
- Market metrics: shares outstanding, float, short interest

### Multi-Timeframe Data Table

Now populated with:
- Weekly bars (from daily aggregation)
- Monthly bars (from daily aggregation)

### Financial Statement Tables

Now populated with:
- `income_statements` - Quarterly/annual income statements
- `balance_sheets` - Quarterly/annual balance sheets
- `cash_flow_statements` - Quarterly/annual/TTM cash flows

## On-Demand Execution

### Via Workflow Orchestrator

```python
from app.workflows.orchestrator import WorkflowOrchestrator
from app.workflows.data_frequency import DataFrequency

orchestrator = WorkflowOrchestrator()
result = orchestrator.execute_workflow(
    workflow_type='on_demand',
    symbols=['AAPL'],
    data_frequency=DataFrequency.DAILY,
    force=True
)
```

### Via API Endpoint

The existing `/api/v1/fetch-historical-data` endpoint now includes all new stages:

```bash
curl -X POST http://localhost:8001/api/v1/fetch-historical-data \
  -H "Content-Type: application/json" \
  -d '{
    "symbol": "AAPL",
    "period": "1y"
  }'
```

This will execute:
1. Data ingestion
2. Indicator computation
3. **Financial data ingestion** (NEW)
4. **Weekly aggregation** (NEW)
5. **Growth calculations** (NEW)
6. Signal generation

## Testing

### Test Weekly Aggregation

```python
from app.services.data_aggregation_service import DataAggregationService

service = DataAggregationService()
result = service.aggregate_to_weekly('AAPL', force=True)
print(result)
```

### Test Growth Calculations

```python
from app.services.growth_calculation_service import GrowthCalculationService

service = GrowthCalculationService()
result = service.calculate_growth_metrics('AAPL', force=True)
print(result)
```

### Test Financial Data Ingestion

```python
from app.data_management.refresh_manager import DataRefreshManager
from app.data_management.refresh_strategy import DataType, RefreshMode

manager = DataRefreshManager()
result = manager.refresh_data(
    symbol='AAPL',
    data_types=[DataType.INCOME_STATEMENTS, DataType.BALANCE_SHEETS, DataType.CASH_FLOW_STATEMENTS],
    mode=RefreshMode.ON_DEMAND,
    force=True
)
print(result)
```

## Verification

### Check Weekly Data

```sql
SELECT * FROM multi_timeframe_data 
WHERE stock_symbol = 'AAPL' AND timeframe = 'weekly' 
ORDER BY date DESC LIMIT 10;
```

### Check Growth Metrics

```sql
SELECT stock_symbol, as_of_date, revenue_growth, earnings_growth, eps_growth
FROM enhanced_fundamentals
WHERE stock_symbol = 'AAPL'
ORDER BY as_of_date DESC;
```

### Check Financial Statements

```sql
SELECT period_end, fiscal_year, fiscal_quarter, revenues, net_income, net_income_per_share
FROM income_statements
WHERE stock_symbol = 'AAPL'
ORDER BY period_end DESC LIMIT 5;
```

## Workflow Audit

All new stages are tracked in:
- `workflow_stage_executions` - Stage-level tracking
- `workflow_symbol_states` - Symbol-level tracking
- `data_fetch_audit` - Data fetch audit trail

## Next Steps

1. ✅ All three operations implemented
2. ✅ Integrated into workflow orchestrator
3. ✅ Database tables created (Migration 019)
4. ⏳ Test with real data
5. ⏳ Verify all data is being populated correctly
6. ⏳ Monitor performance and optimize if needed

## Notes

- Financial data stages are optional (won't fail workflow if unavailable)
- Weekly aggregation requires at least 7 days of daily data
- Growth calculations require at least 2 periods of income statements
- All operations support `force=True` to re-run even if data exists

