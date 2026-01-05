# Data Source Onboarding Guide

## Overview

This guide provides a step-by-step process for onboarding new data sources into the trading system's validation, audit, and retry framework. This framework ensures data quality, provides comprehensive audit trails, and implements automatic retry mechanisms for failed data loads.

## Architecture Overview

The framework consists of three main components:

1. **Data Validation Module** (`app/data_validation/`)
   - Validates incoming data for completeness, quality, and business rules
   - Generates structured validation reports
   - Supports both DataFrame and dictionary-based data

2. **Data Fetch Audit System** (`data_fetch_audit` table)
   - Records all data fetch operations with metadata
   - Links to validation reports for detailed analysis
   - Tracks success/failure status and error messages

3. **Ingestion State Tracking** (`data_ingestion_state` table)
   - Manages retry counts and next retry timestamps
   - Implements staged backoff strategy for failed loads
   - Provides visibility into data pipeline health

## Prerequisites

Before onboarding a new data source, ensure:

- Database tables exist: `data_validation_reports`, `data_fetch_audit`, `data_ingestion_state`
- Core validation framework is imported: `from app.data_validation import *`
- JSON sanitization utility is available: `from app.utils.json_sanitize import json_dumps_sanitized`

## Step 1: Create a Custom Validator

Create a new validator class in `app/data_validation/` that inherits from the base validation patterns:

```python
# app/data_validation/new_source_validator.py

from typing import Dict, Any, List, Optional
from datetime import datetime
from .validator import ValidationReport, ValidationResult, ValidationIssue, ValidationSeverity

class NewSourceValidator:
    """Validator for new data source payloads"""
    
    def __init__(self):
        self.required_fields = [
            'field1',
            'field2', 
            'field3'
        ]
        self.numeric_fields = [
            'field1',
            'field2'
        ]
    
    def validate(self, data: Dict[str, Any], symbol: str, data_type: str) -> ValidationReport:
        """Validate the data payload and return a ValidationReport"""
        
        issues = []
        
        # Check required fields
        for field in self.required_fields:
            if field not in data or data[field] is None:
                issues.append(ValidationIssue(
                    field=field,
                    severity=ValidationSeverity.CRITICAL,
                    message=f"Missing required field: {field}",
                    value=data.get(field),
                    recommendation=f"Ensure {field} is included in the data source"
                ))
        
        # Validate numeric fields
        for field in self.numeric_fields:
            if field in data and data[field] is not None:
                try:
                    value = float(data[field])
                    if value < 0:
                        issues.append(ValidationIssue(
                            field=field,
                            severity=ValidationSeverity.WARNING,
                            message=f"Negative value for {field}",
                            value=value,
                            recommendation="Verify data source accuracy"
                        ))
                except (ValueError, TypeError):
                    issues.append(ValidationIssue(
                        field=field,
                        severity=ValidationSeverity.CRITICAL,
                        message=f"Invalid numeric value for {field}",
                        value=data[field],
                            recommendation="Ensure numeric fields contain valid numbers"
                    ))
        
        # Business logic validations
        if 'field3' in data:
            if not isinstance(data['field3'], str) or len(data['field3'].strip()) == 0:
                issues.append(ValidationIssue(
                    field='field3',
                    severity=ValidationSeverity.WARNING,
                    message="Empty or invalid string value",
                    value=data['field3'],
                    recommendation="Provide meaningful string value"
                ))
        
        # Determine overall status
        critical_issues = [i for i in issues if i.severity == ValidationSeverity.CRITICAL]
        overall_status = "fail" if critical_issues else "pass"
        
        return ValidationReport(
            symbol=symbol,
            data_type=data_type,
            timestamp=datetime.utcnow(),
            overall_status=overall_status,
            validation_result=ValidationResult(
                is_valid=overall_status == "pass",
                issues=issues,
                score=max(0, 100 - len(critical_issues) * 20 - len(issues) * 5)
            )
        )
    
    def summarize_issues(self, report: ValidationReport) -> Dict[str, Any]:
        """Create a summary of issues for audit metadata"""
        critical_count = len([i for i in report.validation_result.issues if i.severity == ValidationSeverity.CRITICAL])
        warning_count = len([i for i in report.validation_result.issues if i.severity == ValidationSeverity.WARNING])
        
        return {
            "validation_status": report.overall_status,
            "critical_issues": critical_count,
            "warning_count": warning_count,
            "total_issues": len(report.validation_result.issues),
            "validation_score": report.validation_result.score,
            "missing_fields": [i.field for i in report.validation_result.issues if "missing" in i.message.lower()]
        }
```

## Step 2: Update the Validation Module Exports

Add your new validator to `app/data_validation/__init__.py`:

```python
# Add to existing imports
from .new_source_validator import NewSourceValidator

# Add to __all__ list
__all__ = [
    # ... existing exports
    "NewSourceValidator"
]
```

## Step 3: Integrate Validation into Data Refresh Manager

Update `app/data_management/refresh_manager.py` to include validation for your data source:

```python
# Add imports at the top
from app.data_validation import NewSourceValidator
from app.utils.json_sanitize import json_dumps_sanitized

# Add method to refresh your data type
def _refresh_new_source(self, symbol: str) -> bool:
    """Refresh new source data with validation and audit"""
    import time
    
    start_time = time.time()
    fetch_success = False
    rows_fetched = 0
    rows_saved = 0
    error_message: Optional[str] = None
    validation_report_id: Optional[str] = None
    
    try:
        # Fetch data from your source
        data = self.data_source.fetch_new_source_data(symbol)
        
        rows_fetched = 1 if data else 0
        if not data:
            error_message = "No data available from new source"
            return False
        
        # Validate the data
        validator = NewSourceValidator()
        validation_report = validator.validate(data, symbol, "new_source")
        validation_report_id = self._save_validation_report(validation_report)
        
        # Create metadata for audit
        summary = validator.summarize_issues(validation_report)
        metadata = {
            **summary,
            "source": self.data_source.name,
        }
        
        # Persist data using sanitized JSON
        query = """
            INSERT INTO new_source_snapshots
            (stock_symbol, as_of_date, source, payload)
            VALUES (:symbol, :as_of_date, :source, CAST(:payload AS JSONB))
            ON CONFLICT (stock_symbol, as_of_date)
            DO UPDATE SET payload = EXCLUDED.payload, source = EXCLUDED.source, updated_at = NOW()
        """
        
        db.execute_update(
            query,
            {
                "symbol": symbol,
                "as_of_date": datetime.utcnow().date(),
                "source": self.data_source.name,
                "payload": json_dumps_sanitized(data),
            },
        )
        rows_saved = 1
        
        # Handle validation failures
        if validation_report.overall_status == "fail":
            fetch_success = False
            error_message = "New source validation failed: missing/invalid required fields"
            self.logger.warning(f"⚠️ New source validation FAILED for {symbol}")
            return False
        
        fetch_success = True
        self.logger.info(f"✅ Saved new source snapshot for {symbol}")
        return True
        
    except Exception as e:
        error_message = str(e)
        self.logger.error(f"Error refreshing new source for {symbol}: {e}", exc_info=True)
        raise
    finally:
        # Audit the fetch operation
        fetch_duration_ms = int((time.time() - start_time) * 1000)
        self._audit_data_fetch(
            symbol=symbol,
            fetch_type='new_source',
            fetch_mode='on_demand',
            data_source=self.data_source.name,
            rows_fetched=rows_fetched,
            rows_saved=rows_saved,
            fetch_duration_ms=fetch_duration_ms,
            success=fetch_success,
            error_message=error_message,
            validation_report_id=validation_report_id,
            metadata=metadata,
        )
```

## Step 4: Update Retry Tracking Logic

Ensure your refresh method uses the enhanced `_update_refresh_tracking` method (already implemented):

```python
# This method automatically handles retry logic with staged backoff:
# - Attempt 1: 6 hours later
# - Attempt 2: 24 hours later  
# - Attempt 3+: 48 hours later

# Call this method in your refresh logic:
self._update_refresh_tracking(
    symbol=symbol,
    data_type=DataType.NEW_SOURCE,  # Add your data type to enum
    status='success' if fetch_success else 'failed',
    error=error_message if not fetch_success else None
)
```

## Step 5: Update Database Schema (if needed)

Create tables for your data snapshots if they don't exist:

```sql
-- Example migration file
CREATE TABLE IF NOT EXISTS new_source_snapshots (
    id SERIAL PRIMARY KEY,
    stock_symbol VARCHAR(20) NOT NULL,
    as_of_date DATE NOT NULL,
    source VARCHAR(100) NOT NULL,
    payload JSONB NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE(stock_symbol, as_of_date)
);

-- Add indexes for performance
CREATE INDEX IF NOT EXISTS idx_new_source_snapshots_symbol_date 
ON new_source_snapshots(stock_symbol, as_of_date DESC);
```

## Step 6: Update Data Source Interface

Ensure your data source class implements the fetch method:

```python
# In your data source class
def fetch_new_source_data(self, symbol: str) -> Optional[Dict[str, Any]]:
    """Fetch data from your new source"""
    try:
        # Implement your data fetching logic
        data = your_api_client.get_data(symbol)
        return data
    except Exception as e:
        self.logger.error(f"Failed to fetch new source data for {symbol}: {e}")
        return None
```

## Step 7: Add to Main Refresh Logic

Update the `refresh_data` method in `RefreshManager` to include your new data type:

```python
def refresh_data(self, symbol: str, data_types: List[DataType] = None) -> Dict[str, bool]:
    """Refresh data for specified types"""
    if data_types is None:
        data_types = [DataType.HISTORICAL_PRICES, DataType.FUNDAMENTALS, DataType.NEW_SOURCE]
    
    results = {}
    
    for data_type in data_types:
        try:
            if data_type == DataType.NEW_SOURCE:
                results[data_type.value] = self._refresh_new_source(symbol)
            # ... existing data types
        except Exception as e:
            self.logger.error(f"Failed to refresh {data_type.value} for {symbol}: {e}")
            results[data_type.value] = False
    
    return results
```

## Step 8: Testing Your Implementation

### Unit Tests

```python
# tests/test_new_source_validator.py
import pytest
from app.data_validation.new_source_validator import NewSourceValidator

def test_valid_data():
    validator = NewSourceValidator()
    data = {
        'field1': 100.0,
        'field2': 50.0,
        'field3': 'valid_string'
    }
    report = validator.validate(data, 'TEST', 'new_source')
    assert report.overall_status == 'pass'

def test_missing_required_field():
    validator = NewSourceValidator()
    data = {
        'field1': 100.0,
        # field2 missing
        'field3': 'valid_string'
    }
    report = validator.validate(data, 'TEST', 'new_source')
    assert report.overall_status == 'fail'
    assert any('missing' in issue.message.lower() for issue in report.validation_result.issues)
```

### Integration Tests

```python
# tests/test_new_source_integration.py
import pytest
from app.data_management.refresh_manager import DataRefreshManager

def test_full_refresh_cycle():
    manager = DataRefreshManager()
    results = manager.refresh_data('TEST', [DataType.NEW_SOURCE])
    assert results['new_source'] is True
    
    # Verify audit record was created
    audit_records = db.execute_query(
        "SELECT * FROM data_fetch_audit WHERE fetch_type = 'new_source'"
    )
    assert len(audit_records) > 0
    
    # Verify validation report was saved
    validation_records = db.execute_query(
        "SELECT * FROM data_validation_reports WHERE data_type = 'new_source'"
    )
    assert len(validation_records) > 0
```

## Step 9: Monitoring and Alerting

### Database Queries for Monitoring

```sql
-- Check failed validations in last 24 hours
SELECT 
    symbol,
    data_type,
    overall_status,
    timestamp,
    validation_score
FROM data_validation_reports 
WHERE overall_status = 'fail' 
    AND timestamp >= NOW() - INTERVAL '24 hours'
ORDER BY timestamp DESC;

-- Check retry counts
SELECT 
    stock_symbol,
    dataset,
    retry_count,
    cursor_ts as next_retry_at,
    status,
    error_message
FROM data_ingestion_state 
WHERE retry_count > 0
ORDER BY retry_count DESC, cursor_ts ASC;

-- Audit summary for new data source
SELECT 
    fetch_type,
    COUNT(*) as total_fetches,
    COUNT(*) FILTER (WHERE success = true) as successful_fetches,
    COUNT(*) FILTER (WHERE success = false) as failed_fetches,
    AVG(fetch_duration_ms) as avg_duration_ms
FROM data_fetch_audit 
WHERE fetch_type = 'new_source'
    AND timestamp >= NOW() - INTERVAL '7 days'
GROUP BY fetch_type;
```

### Alert Configuration

Set up alerts for:
- Validation failure rate > 10% in last hour
- Retry count > 3 for any symbol
- No successful data refresh in 24 hours

## Best Practices

1. **Validation Rules**
   - Start with critical field validation
   - Add business logic checks incrementally
   - Use appropriate severity levels (CRITICAL, WARNING, INFO)

2. **Error Handling**
   - Always validate before persisting data
   - Use structured error messages
   - Include recommendations in validation issues

3. **Performance**
   - Use JSON sanitization for all JSONB inserts
   - Add appropriate database indexes
   - Batch operations when possible

4. **Monitoring**
   - Set up comprehensive logging
   - Monitor validation scores and retry counts
   - Create dashboards for data quality metrics

5. **Testing**
   - Unit test all validation rules
   - Integration test the full refresh cycle
   - Test retry behavior with staged failures

## Troubleshooting

### Common Issues

1. **JSON Serialization Errors**
   - Ensure `json_dumps_sanitized()` is used for all JSONB inserts
   - Check for NaN, Infinity, or numpy types in data

2. **Validation Not Running**
   - Verify validator is imported and instantiated
   - Check that `_save_validation_report()` is called
   - Ensure validation_report_id is passed to audit

3. **Retry Not Working**
   - Verify `_update_refresh_tracking()` is called with correct parameters
   - Check that `data_type` is properly mapped to dataset/interval
   - Ensure cursor_ts is being set correctly

4. **Missing Audit Records**
   - Verify `_audit_data_fetch()` is called in finally block
   - Check that all required parameters are provided
   - Ensure metadata includes validation summary

## Example: Complete Implementation

See the fundamentals implementation for a complete example:
- Validator: `app/data_validation/fundamentals_validator.py`
- Integration: `app/data_management/refresh_manager.py` (lines 870-950)
- Retry logic: `app/data_management/refresh_manager.py` (lines 1312-1371)

This implementation demonstrates all the patterns described in this guide and can be used as a reference for onboarding new data sources.
