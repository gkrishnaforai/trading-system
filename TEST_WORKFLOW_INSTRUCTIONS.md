# Testing New Workflow Stages

## Quick Test Instructions

### Option 1: Run Test Script Inside Docker Container

```bash
# Make sure containers are running
docker-compose up -d

# Copy test scripts into container (if not already there)
docker cp test_workflow_stages.py trading-system-python-worker:/app/test_workflow_stages.py
docker cp verify_workflow_data.py trading-system-python-worker:/app/verify_workflow_data.py

# Copy updated service files (after code changes)
docker cp python-worker/app/services/data_aggregation_service.py trading-system-python-worker:/app/app/services/
docker cp python-worker/app/services/growth_calculation_service.py trading-system-python-worker:/app/app/services/
docker cp python-worker/app/workflows/orchestrator.py trading-system-python-worker:/app/app/workflows/

# Run the comprehensive test script
docker exec -it trading-system-python-worker python3 /app/test_workflow_stages.py

# Or run the quick verification script
docker exec -it trading-system-python-worker python3 /app/verify_workflow_data.py AAPL
```

### Option 2: Test via API (if API server is running)

```bash
# Trigger workflow execution
curl -X POST http://localhost:8001/api/v1/fetch-historical-data \
  -H "Content-Type: application/json" \
  -d '{"symbol": "AAPL", "period": "1y"}'

# Check workflow executions
curl http://localhost:8001/api/v1/workflow/executions?limit=5

# Get workflow summary (replace WORKFLOW_ID)
curl http://localhost:8001/api/v1/workflow/executions/WORKFLOW_ID/summary
```

### Option 3: Test Individual Services

```bash
# Test weekly aggregation
docker exec -it trading-system-python-worker python3 -c "
from app.services.data_aggregation_service import DataAggregationService
service = DataAggregationService()
result = service.aggregate_to_weekly('AAPL', force=True)
print(result)
"

# Test growth calculations
docker exec -it trading-system-python-worker python3 -c "
from app.services.growth_calculation_service import GrowthCalculationService
service = GrowthCalculationService()
result = service.calculate_growth_metrics('AAPL', force=True)
print(result)
"

# Test financial data refresh
docker exec -it trading-system-python-worker python3 -c "
from app.data_management.refresh_manager import DataRefreshManager
from app.data_management.refresh_strategy import DataType, RefreshMode
manager = DataRefreshManager()
result = manager.refresh_data(
    symbol='AAPL',
    data_types=[DataType.INCOME_STATEMENTS, DataType.BALANCE_SHEETS, DataType.CASH_FLOW_STATEMENTS],
    mode=RefreshMode.ON_DEMAND,
    force=True
)
print(f'Total: {result.total_requested}, Success: {result.total_successful}, Failed: {result.total_failed}')
"
```

## Verify Data in Database

### Check Workflow Executions

```sql
SELECT workflow_id, workflow_type, status, current_stage, started_at, completed_at
FROM workflow_executions
ORDER BY started_at DESC
LIMIT 5;
```

### Check Workflow Stages

```sql
SELECT stage_name, status, symbols_succeeded, symbols_failed, started_at, completed_at
FROM workflow_stage_executions
WHERE workflow_id = 'YOUR_WORKFLOW_ID'
ORDER BY started_at ASC;
```

### Check Financial Data

```sql
-- Income Statements
SELECT COUNT(*) as count, MAX(period_end) as latest
FROM income_statements
WHERE stock_symbol = 'AAPL';

-- Balance Sheets
SELECT COUNT(*) as count, MAX(period_end) as latest
FROM balance_sheets
WHERE stock_symbol = 'AAPL';

-- Cash Flow Statements
SELECT COUNT(*) as count, MAX(period_end) as latest
FROM cash_flow_statements
WHERE stock_symbol = 'AAPL';
```

### Check Enhanced Fundamentals

```sql
SELECT as_of_date, revenue_growth, earnings_growth, eps_growth, pe_ratio, market_cap
FROM enhanced_fundamentals
WHERE stock_symbol = 'AAPL'
ORDER BY as_of_date DESC
LIMIT 1;
```

### Check Weekly Aggregation

```sql
SELECT COUNT(*) as count, MIN(date) as earliest, MAX(date) as latest
FROM multi_timeframe_data
WHERE stock_symbol = 'AAPL' AND timeframe = 'weekly';

-- Sample weekly bars
SELECT date, open, high, low, close, volume
FROM multi_timeframe_data
WHERE stock_symbol = 'AAPL' AND timeframe = 'weekly'
ORDER BY date DESC
LIMIT 10;
```

## Check Streamlit UI

1. Open Streamlit UI: http://localhost:8501
2. Navigate to "Workflow Engine Lifecycle Testbed"
3. Select "📋 Workflow Audit History"
4. Select a recent workflow execution
5. Verify you see the new stages:
   - `financial_data`
   - `weekly_aggregation`
   - `growth_calculations`

## Expected Results

After running the workflow for AAPL, you should see:

1. ✅ **Workflow Execution** created with status `completed`
2. ✅ **Stages** including:
   - `ingestion` ✅
   - `indicators` ✅
   - `financial_data` ✅ (NEW)
   - `weekly_aggregation` ✅ (NEW)
   - `growth_calculations` ✅ (NEW)
   - `signals` ✅
3. ✅ **Financial Data**:
   - Income statements (multiple records)
   - Balance sheets (multiple records)
   - Cash flow statements (multiple records)
4. ✅ **Enhanced Fundamentals**:
   - Revenue growth, earnings growth, EPS growth
   - P/E ratio, market cap, etc.
5. ✅ **Weekly Aggregation**:
   - Weekly bars in `multi_timeframe_data` table

## Troubleshooting

### If financial data is missing:

- Check if Massive.com API key is configured
- Check if `fetch_comprehensive_financials()` is working
- Check logs: `docker logs trading-system-python-worker`

### If weekly aggregation is missing:

- Ensure daily price data exists (at least 7 days)
- Check if `DataAggregationService` is being called
- Verify `multi_timeframe_data` table exists

### If growth calculations are missing:

- Ensure income statements exist (at least 2 periods)
- Check if periods are comparable (same quarter/year)
- Verify `enhanced_fundamentals` table exists

### Check Logs:

```bash
# Python worker logs
docker logs trading-system-python-worker --tail 100

# Streamlit logs
docker logs trading-system-streamlit --tail 100
```
