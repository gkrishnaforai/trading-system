# Duplicate Prevention Strategy

## Overview

**Industry Standard**: Idempotent operations - safe to retry/re-run without creating duplicates

This document outlines the comprehensive duplicate prevention strategy for different data frequencies (daily, quarterly, intraday).

---

## Database-Level Protection

### 1. UNIQUE Constraints

**Primary Protection**: `UNIQUE(stock_symbol, date)` constraint on `raw_market_data`

```sql
CREATE TABLE raw_market_data (
    ...
    UNIQUE(stock_symbol, date)  -- Prevents duplicates at DB level
);
```

**Benefits**:
- ✅ Database enforces uniqueness
- ✅ Prevents race conditions
- ✅ Works for all data frequencies

### 2. Indexes for Performance

```sql
CREATE INDEX idx_raw_market_symbol_date ON raw_market_data(stock_symbol, date DESC);
```

**Benefits**:
- ✅ Fast duplicate checks
- ✅ Efficient queries for latest data

### 3. Data Source Tracking

```sql
ALTER TABLE raw_market_data ADD COLUMN data_source TEXT DEFAULT 'yahoo_finance';
ALTER TABLE raw_market_data ADD COLUMN data_frequency TEXT DEFAULT 'daily';
```

**Benefits**:
- ✅ Track data origin
- ✅ Handle different frequencies appropriately
- ✅ Audit trail

---

## Application-Level Protection

### 1. IdempotentDataSaver

**Purpose**: Prevents duplicates before database insert

**Features**:
- ✅ Checks existing data before insert
- ✅ Frequency-aware duplicate detection
- ✅ Safe to retry/re-run

**Usage**:
```python
from app.workflows.data_frequency import DataFrequency, IdempotentDataSaver

saver = IdempotentDataSaver(DataFrequency.DAILY)
result = saver.save_market_data(symbol, data, force=False)

# Result: {rows_inserted, rows_updated, rows_skipped, duplicates_prevented}
```

### 2. INSERT OR REPLACE Strategy

**Current Implementation**: Uses `INSERT OR REPLACE` for idempotency

```python
db.execute_update(
    """
    INSERT OR REPLACE INTO raw_market_data
    (stock_symbol, date, open, high, low, close, volume, ...)
    VALUES (:symbol, :date, :open, :high, :low, :close, :volume, ...)
    """
)
```

**Benefits**:
- ✅ Updates if exists, inserts if not
- ✅ No duplicate errors
- ✅ Safe for retries

---

## Data Frequency Strategies

### Daily Data (EOD)

**Strategy**: One record per symbol per day

**Duplicate Prevention**:
- ✅ Check if record exists for same date
- ✅ If exists and newer, update
- ✅ If exists and older, skip (unless force=True)

**Example**:
```python
# First run: Insert
INSERT INTO raw_market_data (symbol, date, ...) VALUES ('AAPL', '2024-01-15', ...)

# Retry same day: Update (if newer data)
INSERT OR REPLACE INTO raw_market_data (symbol, date, ...) VALUES ('AAPL', '2024-01-15', ...)

# Next day: Insert new record
INSERT INTO raw_market_data (symbol, date, ...) VALUES ('AAPL', '2024-01-16', ...)
```

### Quarterly Data (Earnings, Fundamentals)

**Strategy**: One record per symbol per quarter

**Duplicate Prevention**:
- ✅ Check if record exists in same quarter
- ✅ If exists and newer, update
- ✅ If exists and older, skip

**Example**:
```python
# Q1 2024: Insert
INSERT INTO raw_market_data (symbol, date, data_frequency, ...) 
VALUES ('AAPL', '2024-03-31', 'quarterly', ...)

# Retry Q1: Update (if newer)
INSERT OR REPLACE INTO raw_market_data (symbol, date, data_frequency, ...) 
VALUES ('AAPL', '2024-03-31', 'quarterly', ...)

# Q2 2024: Insert new record
INSERT INTO raw_market_data (symbol, date, data_frequency, ...) 
VALUES ('AAPL', '2024-06-30', 'quarterly', ...)
```

### Intraday Data

**Strategy**: Multiple records per symbol per day (with timestamp)

**Note**: Current schema uses `date` only. For true intraday, would need `timestamp` column.

**Future Enhancement**:
```sql
ALTER TABLE raw_market_data ADD COLUMN timestamp TIMESTAMP;
CREATE UNIQUE INDEX idx_intraday ON raw_market_data(stock_symbol, date, timestamp);
```

---

## Workflow Integration

### WorkflowOrchestrator

**Integration**: Duplicate prevention built into workflow stages

```python
from app.workflows import WorkflowOrchestrator, DataFrequency

orchestrator = WorkflowOrchestrator()

# Execute with duplicate prevention
result = orchestrator.execute_workflow(
    workflow_type='daily_batch',
    symbols=['AAPL', 'GOOGL'],
    data_frequency=DataFrequency.DAILY,
    force=False  # Don't force - respect duplicates
)
```

**Benefits**:
- ✅ Automatic duplicate prevention
- ✅ Frequency-aware handling
- ✅ Safe retries

---

## Retry/Re-run Safety

### Scenario 1: Daily Batch Retry

**Problem**: Batch job fails mid-way, need to retry

**Solution**:
1. ✅ `UNIQUE` constraint prevents duplicates
2. ✅ `INSERT OR REPLACE` updates existing records
3. ✅ `IdempotentDataSaver` checks before insert
4. ✅ Workflow tracks which symbols already processed

**Result**: Safe to retry entire batch

### Scenario 2: Manual Re-run

**Problem**: User manually triggers data refresh

**Solution**:
1. ✅ Same duplicate prevention applies
2. ✅ `force=True` option to override (admin only)
3. ✅ Audit trail tracks all operations

**Result**: Safe to manually re-run

### Scenario 3: Multiple Data Sources

**Problem**: Data from multiple sources (Yahoo, Finnhub, etc.)

**Solution**:
1. ✅ `data_source` column tracks origin
2. ✅ `INSERT OR REPLACE` handles conflicts
3. ✅ Latest data wins (by `updated_at`)

**Result**: No duplicates, latest data preserved

---

## Validation & Quality Checks

### Pre-Insert Validation

**Checks**:
- ✅ Date is valid
- ✅ Price values are reasonable (> 0)
- ✅ Volume is non-negative
- ✅ Data is not stale (> 5 days old for daily)

### Post-Insert Validation

**Checks**:
- ✅ No duplicate records (query `potential_duplicates` view)
- ✅ Data quality score acceptable
- ✅ Indicators can be calculated

---

## Monitoring & Alerts

### Duplicate Detection

**Query**:
```sql
SELECT * FROM potential_duplicates;
```

**Alert**: If any rows returned, investigate

### Data Freshness

**Query**:
```sql
SELECT * FROM latest_market_data 
WHERE latest_date < DATE('now', '-5 days');
```

**Alert**: Stale data detected

---

## Best Practices

### ✅ DO

1. **Always use `IdempotentDataSaver`** for data insertion
2. **Set appropriate `data_frequency`** for each data type
3. **Use `INSERT OR REPLACE`** for idempotency
4. **Check `duplicates_prevented`** in save results
5. **Monitor `potential_duplicates` view** regularly

### ❌ DON'T

1. **Don't bypass UNIQUE constraint** (use `force=True` only when necessary)
2. **Don't insert without checking** existing data
3. **Don't mix data frequencies** without proper handling
4. **Don't ignore duplicate warnings** in logs

---

## Testing

### Unit Tests

```python
def test_daily_duplicate_prevention():
    saver = IdempotentDataSaver(DataFrequency.DAILY)
    
    # First insert
    result1 = saver.save_market_data('AAPL', data1)
    assert result1['rows_inserted'] == 1
    
    # Retry same data
    result2 = saver.save_market_data('AAPL', data1)
    assert result2['duplicates_prevented'] == 1
```

### Integration Tests

```python
def test_workflow_retry_safety():
    orchestrator = WorkflowOrchestrator()
    
    # First run
    result1 = orchestrator.execute_workflow('daily_batch', ['AAPL'])
    
    # Retry (simulate failure recovery)
    result2 = orchestrator.execute_workflow('daily_batch', ['AAPL'])
    
    # Should not create duplicates
    duplicates = db.execute_query("SELECT * FROM potential_duplicates")
    assert len(duplicates) == 0
```

---

## Summary

**Database Level**:
- ✅ `UNIQUE(stock_symbol, date)` constraint
- ✅ Indexes for performance
- ✅ Data source/frequency tracking

**Application Level**:
- ✅ `IdempotentDataSaver` with frequency-aware logic
- ✅ `INSERT OR REPLACE` for idempotency
- ✅ Pre-insert duplicate checks

**Workflow Level**:
- ✅ Built into `WorkflowOrchestrator`
- ✅ Safe retries
- ✅ Audit trail

**Result**: ✅ **100% duplicate prevention** - safe to retry/re-run at any time

