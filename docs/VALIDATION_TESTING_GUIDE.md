# Data Validation Testing Guide

## Quick Test Commands

### 1. Apply Migration (if not already done)

```bash
# SQLite
sqlite3 db/trading.db < db/migrations/011_add_data_validation.sql

# Verify table exists
sqlite3 db/trading.db ".schema data_validation_reports"
```

### 2. Test with TQQQ via Python Script

```bash
# Run test script (requires services to be running)
docker-compose exec python-worker python scripts/test_validation.py

# Or run directly if Python environment is set up
python scripts/test_validation.py
```

### 3. Test via API (requires services running)

```bash
# Fetch data for TQQQ (triggers validation)
curl -X POST http://localhost:8001/api/v1/fetch-historical-data \
  -H "Content-Type: application/json" \
  -d '{
    "symbol": "TQQQ",
    "period": "1y",
    "calculate_indicators": true
  }' | jq '.results.price_historical.validation'

# Generate swing signal (shows diagnostics)
curl -X POST http://localhost:8001/api/v1/swing/signal \
  -H "Content-Type: application/json" \
  -d '{
    "symbol": "TQQQ",
    "user_id": "user1"
  }' | jq '.reason'
```

### 4. Query Validation Reports from Database

```bash
# Get latest validation report for TQQQ
sqlite3 db/trading.db "
SELECT 
    symbol,
    data_type,
    overall_status,
    critical_issues,
    warnings,
    rows_dropped,
    datetime(validation_timestamp) as timestamp
FROM data_validation_reports
WHERE symbol = 'TQQQ'
ORDER BY validation_timestamp DESC
LIMIT 1;
"

# Get full validation report JSON
sqlite3 db/trading.db "
SELECT report_json FROM data_validation_reports 
WHERE symbol = 'TQQQ' 
ORDER BY validation_timestamp DESC 
LIMIT 1;
" | python3 -m json.tool

# Summary statistics
sqlite3 db/trading.db "
SELECT 
    COUNT(*) as total_reports,
    COUNT(DISTINCT symbol) as unique_symbols,
    SUM(critical_issues) as total_critical,
    SUM(warnings) as total_warnings,
    AVG(rows_dropped) as avg_rows_dropped
FROM data_validation_reports;
"
```

### 5. Test via Streamlit UI

1. **Start services**:
   ```bash
   docker-compose up -d
   ```

2. **Open Streamlit**:
   - Navigate to `http://localhost:8501`
   - Go to **📈 Swing Trading** page
   - Enter symbol: `TQQQ`
   - Click **📥 Fetch Data First**
   - Review the detailed validation report shown below

3. **Or use Testbed**:
   - Navigate to **🧪 Testbed** page
   - Select **📥 Fetch Data** section
   - Enter symbol: `TQQQ`
   - Click **🚀 Fetch All Data**
   - Expand each data type to see validation details

## Expected Results

### Successful Validation

- **Overall Status**: `pass` or `warning`
- **Critical Issues**: `0`
- **Rows Dropped**: Low number (0-5% of total)
- **Validation Checks**: Most checks should pass

### Failed Validation

- **Overall Status**: `fail`
- **Critical Issues**: > 0
- **Common Issues**:
  - Missing values in critical columns
  - Negative prices or invalid ranges
  - Non-numeric data in numeric columns

### Swing Signal Diagnostics

When swing signal shows "Insufficient indicator data", the reason should now include:
- Total candles count
- Valid EMA9/EMA21 point counts
- Rows dropped due to NaN
- Clear explanation and fix recommendation

## Troubleshooting

### No Validation Reports in Database

**Check**:
1. Migration was applied: `sqlite3 db/trading.db ".schema data_validation_reports"`
2. Data was fetched after migration was applied
3. Validation is running (check Python worker logs)

**Solution**:
- Re-fetch data for the symbol
- Check Python worker logs for validation messages
- Verify `DataRefreshManager._refresh_price_historical()` is calling validator

### Validation Not Running

**Check Python worker logs**:
```bash
docker-compose logs python-worker | grep -i validation
```

**Expected log messages**:
```
🔍 Validating price_historical data for TQQQ: 251 rows, 6 columns
✅ Validation complete for TQQQ: PASS (0 critical, 2 warnings, 12 rows would be dropped)
🧹 Cleaned TQQQ data: 251 → 239 rows (12 dropped)
```

### Swing Signal Still Shows Generic Message

**Check**:
1. Latest code is deployed (SwingTrendStrategy updated)
2. Python worker was restarted after code changes
3. Signal was generated after code update

**Solution**:
- Restart Python worker: `docker-compose restart python-worker`
- Re-generate swing signal
- Check that `entry_reason` includes detailed diagnostics

## Next Steps

1. ✅ **Migration Applied**: Table `data_validation_reports` exists
2. ⏭️ **Test with TQQQ**: Fetch data and review validation report
3. ⏭️ **Review Reports**: Check database for validation history
4. ⏭️ **Monitor**: Track validation reports over time for data quality trends

