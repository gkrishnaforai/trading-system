# Data Validation Guide

## Overview

The Trading System now includes comprehensive data validation to ensure data quality before calculations and signal generation. This is **critical** because bad source data leads to incorrect calculations and unreliable signals.

## Architecture

### Validation Module

Located in `python-worker/app/data_validation/`:

- **`validator.py`**: Main `DataValidator` class that orchestrates all checks
- **`checks.py`**: Individual validation check classes:
  - `MissingValuesCheck`: Detects missing values in critical columns
  - `DuplicateCheck`: Finds duplicate rows
  - `DataTypeCheck`: Ensures numeric columns are numeric
  - `RangeCheck`: Validates price/volume ranges (positive, high >= low, etc.)
  - `OutlierCheck`: Detects statistical outliers using IQR method
  - `ContinuityCheck`: Checks for gaps in time series
  - `VolumeCheck`: Validates volume data quality

### Validation Severity Levels

- **CRITICAL**: Data unusable, must fix (e.g., negative prices, high < low)
- **WARNING**: Data quality concern, may affect accuracy (e.g., >10% missing values, outliers)
- **INFO**: Minor issue, data still usable

### Validation Report Structure

```python
ValidationReport(
    symbol: str,
    data_type: str,
    timestamp: datetime,
    total_rows: int,
    total_columns: int,
    rows_after_cleaning: int,
    rows_dropped: int,
    validation_results: List[ValidationResult],
    overall_status: str,  # "pass", "warning", "fail"
    critical_issues: int,
    warnings: int,
    recommendations: List[str]
)
```

## Database Schema

### `data_validation_reports` Table

```sql
CREATE TABLE data_validation_reports (
    report_id TEXT PRIMARY KEY,
    symbol TEXT NOT NULL,
    data_type TEXT NOT NULL,
    validation_timestamp TIMESTAMP NOT NULL,
    report_json TEXT NOT NULL,  -- Full ValidationReport as JSON
    overall_status TEXT NOT NULL CHECK(overall_status IN ('pass', 'warning', 'fail')),
    critical_issues INTEGER DEFAULT 0,
    warnings INTEGER DEFAULT 0,
    rows_dropped INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

## Integration Points

### 1. Data Refresh Pipeline

Validation is **automatically** integrated into `DataRefreshManager._refresh_price_historical()`:

```python
# Fetch data
data = self.data_source.fetch_price_data(symbol, period="1y")

# Validate data
validation_report = validator.validate(data, symbol, "price_historical")

# Clean data (remove bad rows)
cleaned_data, cleaned_report = validator.validate_and_clean(data, symbol, "price_historical")

# Save validation report to database
self._save_validation_report(cleaned_report)

# Save cleaned data
rows_saved = fetcher.save_raw_market_data(symbol, cleaned_data)
```

### 2. API Endpoints

Validation reports are included in API responses:

- **`/api/v1/fetch-historical-data`**: Returns validation report in `results.price_historical.validation`
- **`/api/v1/refresh-data`**: Includes validation in refresh results

### 3. Swing Strategy Diagnostics

`SwingTrendStrategy` now provides detailed diagnostics when indicators are insufficient:

```
Total candles: 251
Valid EMA9 points: 5 (need ≥2)
Valid EMA21 points: 3 (need ≥2)
Rows with NaN in critical columns: 12
⚠️ 12 rows dropped due to NaN values
💡 The EMA series derived from the candles don't have enough valid points at the tail (due to NaNs/dropped rows/data quality issues), so failing safe with HOLD.
💡 Re-fetch historical data with indicators for this symbol to fix it.
```

## Usage

### Automatic Validation

Validation runs **automatically** when:
- Fetching historical price data via `/api/v1/fetch-historical-data`
- Refreshing price data via `/api/v1/refresh-data`

### Manual Validation

You can also validate data manually:

```python
from app.data_validation import DataValidator
import pandas as pd

validator = DataValidator()
report = validator.validate(data, symbol="TQQQ", data_type="price_historical")

# Check status
if report.overall_status == "fail":
    print(f"❌ Critical issues: {report.critical_issues}")
    for result in report.validation_results:
        if not result.passed:
            for issue in result.issues:
                print(f"  - {issue.message}")

# Clean data
cleaned_data, cleaned_report = validator.validate_and_clean(data, symbol="TQQQ")
```

### Viewing Validation Reports

#### Via Database

```sql
-- Get latest validation report for a symbol
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

-- Get full report JSON
SELECT report_json FROM data_validation_reports 
WHERE symbol = 'TQQQ' 
ORDER BY validation_timestamp DESC LIMIT 1;

-- Summary statistics
SELECT 
    COUNT(*) as total_reports,
    COUNT(DISTINCT symbol) as unique_symbols,
    SUM(critical_issues) as total_critical,
    SUM(warnings) as total_warnings,
    AVG(rows_dropped) as avg_rows_dropped
FROM data_validation_reports;
```

#### Via Streamlit UI

1. **Swing Trading Page**: After fetching data, validation report is shown in the detailed results
2. **Stock Analysis Page**: Validation report appears after data fetch
3. **Testbed Page**: Full validation details in "Fetch Data" section

## Validation Checks Explained

### 1. Missing Values Check

- **What it checks**: Missing values in critical columns (close, high, low, open, volume)
- **Severity**: CRITICAL if >10% missing, WARNING otherwise
- **Recommendation**: Fill missing values or remove affected rows

### 2. Duplicate Check

- **What it checks**: Duplicate rows in the dataset
- **Severity**: CRITICAL if >5% duplicates, WARNING otherwise
- **Recommendation**: Remove duplicate rows

### 3. Data Type Check

- **What it checks**: Numeric columns are actually numeric
- **Severity**: CRITICAL if cannot convert, WARNING if can convert
- **Recommendation**: Fix non-numeric values or convert types

### 4. Range Check

- **What it checks**: 
  - Prices are positive
  - High >= Low
  - Volume is non-negative
- **Severity**: CRITICAL
- **Recommendation**: Fix invalid ranges (data corruption)

### 5. Outlier Check

- **What it checks**: Statistical outliers using IQR method (3x IQR)
- **Severity**: WARNING (outliers can be valid market events)
- **Recommendation**: Review outliers - may be splits, crashes, or data errors

### 6. Continuity Check

- **What it checks**: Large gaps (>7 days) in time series
- **Severity**: WARNING
- **Recommendation**: Review gaps - may indicate missing data periods

### 7. Volume Check

- **What it checks**: Zero-volume days
- **Severity**: WARNING if >20% zero volume
- **Recommendation**: Review zero-volume days - may indicate data quality issues

## Best Practices

### 1. Always Review Validation Reports

After fetching data, check the validation report:
- If `overall_status == "fail"`: Fix critical issues before using data
- If `overall_status == "warning"`: Review warnings and decide if action is needed
- If `overall_status == "pass"`: Data is clean and ready to use

### 2. Monitor Validation History

Track validation reports over time to identify:
- Symbols with consistent data quality issues
- Data source problems
- Patterns in data corruption

### 3. Fix Issues at Source

When validation fails:
1. Check the data source (Yahoo Finance, Finnhub, etc.)
2. Review the specific validation issues
3. Re-fetch data if source issue is resolved
4. Consider using fallback data sources

### 4. Use Cleaned Data

The validator provides `validate_and_clean()` which:
- Removes rows with critical issues
- Drops duplicates
- Removes rows with NaN in critical columns

**Note**: Always review what was dropped before using cleaned data.

## Troubleshooting

### "Insufficient indicator data" in Swing Strategy

**Cause**: EMA series don't have enough valid points after data cleaning.

**Solution**:
1. Check validation report for the symbol
2. Review `rows_dropped` - if high, data quality is poor
3. Re-fetch data from a different source
4. Check for missing values or data gaps

### High `rows_dropped` Count

**Possible causes**:
- Data source has many missing values
- Data corruption (negative prices, invalid ranges)
- Time series gaps

**Solution**:
1. Review validation report details
2. Check data source quality
3. Try alternative data source (fallback mechanism)
4. Manually clean data if needed

### Validation Report Not Appearing

**Check**:
1. Migration `011_add_data_validation.sql` was applied
2. `data_validation_reports` table exists
3. Validation is running (check logs for validation messages)
4. API response includes `validation` field

## Example Validation Report

```json
{
  "symbol": "TQQQ",
  "data_type": "price_historical",
  "timestamp": "2025-01-15T10:30:00",
  "total_rows": 251,
  "total_columns": 6,
  "rows_after_cleaning": 239,
  "rows_dropped": 12,
  "overall_status": "warning",
  "critical_issues": 0,
  "warnings": 2,
  "validation_results": [
    {
      "check_name": "MissingValuesCheck",
      "passed": false,
      "severity": "warning",
      "rows_checked": 251,
      "rows_failed": 8,
      "issues": [
        {
          "message": "Column 'volume' has 8 missing values (3.2%)",
          "severity": "warning",
          "affected_columns": ["volume"],
          "recommendation": "Fill missing values in 'volume' or remove affected rows"
        }
      ]
    },
    {
      "check_name": "OutlierCheck",
      "passed": false,
      "severity": "warning",
      "issues": [
        {
          "message": "Found 5 potential outliers (2.0%) using IQR method",
          "severity": "warning",
          "recommendation": "Review outliers - they may be valid market events (splits, crashes) or data errors"
        }
      ]
    }
  ],
  "recommendations": [
    "Consider using forward-fill or interpolation for missing values",
    "Review outliers - they may be valid market events or data errors"
  ]
}
```

## Migration

The validation system requires migration `011_add_data_validation.sql`:

```bash
# Apply migration manually
sqlite3 db/trading.db < db/migrations/011_add_data_validation.sql

# Or let the system apply it automatically on startup
# (migration is in database.py migration list)
```

## Summary

Data validation is now **automatically integrated** into the data refresh pipeline. Every time price data is fetched:

1. ✅ Data is validated
2. ✅ Bad rows are identified and dropped
3. ✅ Validation report is generated and saved
4. ✅ Detailed results are returned to UI
5. ✅ Swing strategy diagnostics include validation insights

This ensures **data quality at the source**, preventing bad data from affecting calculations and signals.

