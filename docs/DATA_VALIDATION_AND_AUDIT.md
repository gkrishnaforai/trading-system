# Data Validation and Audit System

## Overview

This document describes the comprehensive data validation and audit system implemented to ensure data quality and signal readiness for the trading system.

## Industry Standards (December 2025)

Based on industry research, the following best practices are implemented:

1. **Multi-Source Data Validation**: Validate data from multiple sources to ensure completeness
2. **Indicator Data Availability Checks**: Verify data supports required technical indicator calculations
3. **Signal Readiness Validation**: Check if data is ready for signal generation before executing strategies
4. **Comprehensive Audit Trail**: Track all data fetch operations with detailed metadata
5. **Fail-Fast Error Handling**: No workarounds or fallbacks - fail fast with detailed error messages

## Components

### 1. Data Validation Module (`app/data_validation/`)

#### Validation Checks

1. **MissingValuesCheck**: Checks for missing values in critical columns (close, high, low, open, volume)
2. **DuplicateCheck**: Identifies duplicate rows based on date
3. **DataTypeCheck**: Validates numeric columns are actually numeric
4. **RangeCheck**: Ensures prices are positive and high >= low
5. **OutlierCheck**: Detects statistical outliers using IQR method
6. **ContinuityCheck**: Checks for gaps in time series data
7. **VolumeCheck**: Validates volume data quality
8. **IndicatorDataCheck**: **NEW** - Validates data supports indicator calculations

#### IndicatorDataCheck Details

The `IndicatorDataCheck` validates:
- Sufficient data periods for each indicator (EMA9: 9, EMA21: 21, SMA50: 50, RSI14: 14, MACD: 26, ATR14: 14)
- Valid data at the tail (at least 2 valid values for EMA calculations)
- Data quality for swing trading signals (minimum 50 periods, preferably 200+)

### 2. Data Fetch Audit System

#### Database Tables

**`data_fetch_audit`**: Tracks all data fetch operations
- `audit_id`: Unique identifier
- `symbol`: Stock symbol
- `fetch_type`: Type of data fetched (price_historical, fundamentals, etc.)
- `fetch_mode`: Mode (scheduled, on_demand, periodic, live)
- `data_source`: Source used (yahoo_finance, finnhub, etc.)
- `rows_fetched`: Number of rows fetched
- `rows_saved`: Number of rows saved
- `fetch_duration_ms`: Duration in milliseconds
- `success`: Boolean success flag
- `error_message`: Error message if failed
- `validation_report_id`: Reference to validation report
- `metadata`: JSON metadata

**`signal_readiness`**: Tracks signal readiness status
- `readiness_id`: Unique identifier
- `symbol`: Stock symbol
- `signal_type`: Type of signal (swing_trend, technical, hybrid_llm)
- `readiness_status`: Status (ready, not_ready, partial)
- `required_indicators`: JSON array of required indicators
- `available_indicators`: JSON array of available indicators
- `missing_indicators`: JSON array of missing indicators
- `data_quality_score`: Score from 0.0 to 1.0
- `validation_report_id`: Reference to validation report
- `readiness_reason`: Why signal is ready/not ready
- `recommendations`: JSON array of recommendations

### 3. Signal Readiness Validator

The `SignalReadinessValidator` checks if data is ready for signal generation:

#### Signal Type Requirements

**swing_trend**:
- Required indicators: EMA9, EMA21, SMA50, RSI, MACD, ATR
- Minimum periods: 50
- Minimum valid tail: 2 values
- Data quality threshold: 0.8

**technical**:
- Required indicators: EMA20, SMA50, SMA200, RSI, MACD
- Minimum periods: 200
- Minimum valid tail: 1 value
- Data quality threshold: 0.7

**hybrid_llm**:
- Required indicators: EMA20, SMA50, RSI, MACD
- Minimum periods: 200
- Minimum valid tail: 1 value
- Data quality threshold: 0.7

#### Readiness Status

- **ready**: All checks passed, data is ready for signal generation
- **not_ready**: Critical issues prevent signal generation
- **partial**: Data quality below threshold but may still be usable

### 4. EMA Calculation Fix

The EMA calculation has been enhanced to handle NaN values properly:

1. **Forward Fill**: Uses last known value for missing periods
2. **Backward Fill**: Fills leading NaNs if needed
3. **Preserve Gaps**: Restores original NaNs where input was NaN (preserves data gaps)
4. **Validation**: Checks for sufficient valid data before calculation

### 5. API Endpoints

#### Data Fetch Audit
- `GET /api/v1/data-fetch-audit/{symbol}`: Get fetch audit history for a symbol

#### Signal Readiness
- `GET /api/v1/signal-readiness/{symbol}?signal_type=swing_trend`: Check signal readiness

#### Enhanced Swing Signal
- `POST /api/v1/swing/signal`: Now includes signal readiness check before generating signal

## Usage

### Checking Signal Readiness

```python
from app.data_validation.signal_readiness import SignalReadinessValidator

validator = SignalReadinessValidator()
result = validator.check_readiness(symbol="TQQQ", signal_type="swing_trend")

if result.readiness_status == 'ready':
    # Generate signal
    pass
else:
    # Handle not ready case
    print(f"Not ready: {result.readiness_reason}")
    print(f"Recommendations: {result.recommendations}")
```

### Viewing Data Fetch History

```python
# Via API
GET /api/v1/data-fetch-audit/TQQQ?limit=20

# Returns:
{
    "symbol": "TQQQ",
    "audit_records": [
        {
            "audit_id": "...",
            "fetch_type": "price_historical",
            "fetch_mode": "on_demand",
            "timestamp": "2025-01-15T10:30:00",
            "data_source": "YahooFinanceDataSource",
            "rows_fetched": 251,
            "rows_saved": 251,
            "fetch_duration_ms": 1234,
            "success": true,
            "validation_report_id": "..."
        }
    ],
    "count": 1
}
```

## Validation Flow

1. **Data Fetch**: Fetch data from source
2. **Data Validation**: Run all validation checks
3. **Data Cleaning**: Remove bad rows based on validation results
4. **Audit Logging**: Log fetch operation to `data_fetch_audit`
5. **Indicator Calculation**: Calculate indicators if validation passed
6. **Signal Readiness Check**: Check if data is ready for signal generation
7. **Signal Generation**: Generate signal if ready

## Error Handling

- **Fail Fast**: No workarounds or fallbacks
- **Detailed Errors**: All errors include actionable recommendations
- **Audit Trail**: All operations are logged for debugging

## Future Enhancements

1. **Multi-Source Validation**: Compare data from multiple sources
2. **Automated Data Quality Reports**: Generate reports on data quality trends
3. **Alert System Integration**: Alert on data quality issues
4. **Data Quality Dashboard**: Visual dashboard for data quality metrics

