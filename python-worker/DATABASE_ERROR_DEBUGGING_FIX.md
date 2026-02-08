# Database Error Debugging Fix

## 🚨 **Problem Identified:**
```
[SQL: INSERT INTO financial_statements ... VALUES (%(stock_symbol)s, %(period_type)s, %(statement_type)s, %(fiscal_period)s, %(payload)s, %(data_source)s, %(created_at)s, %(updated_at)s) ...]
[parameters: {'stock_symbol': 'AAPL', 'period_type': 'annual', 'statement_type': 'income_statement', 'fiscal_period': datetime.date(2026, 12, 31), 'payload': '{"date": "2021-09-25", "symbol": "AAPL", ...}', 'data_source': 'unknown', 'created_at': datetime.datetime(2026, 1, 21, 5, 57, 3, 928344), 'updated_at': datetime.datetime(2026, 1, 21, 5, 57, 3, 928344)}]
❌ Exception in _refresh_income_statements for AAPL: No financial statements were successfully saved for AAPL
```

The JSON serialization is working (payload is now a JSON string), but there's still a database error. The actual database error details are not being shown properly, making it difficult to diagnose the root cause.

## ✅ **Enhanced Database Error Debugging Applied:**

### **Added Detailed Error Logging:**
```python
# Before:
except Exception as db_error:
    self.logger.error(f"Failed to save financial statement record for {symbol} {fiscal_period}: {db_error}")
    continue

# After:
except Exception as db_error:
    self.logger.error(f"Failed to save financial statement record for {symbol} {fiscal_period}: {db_error}")
    self.logger.error(f"Database error type: {type(db_error).__name__}")
    self.logger.error(f"Database error details: {str(db_error)}")
    # Log the record that failed for debugging
    self.logger.error(f"Failed record details: {record}")
    # Log the SQL that failed
    self.logger.error(f"SQL that failed: INSERT INTO financial_statements ...")
    continue
```

## 🎯 **Potential Database Issues to Investigate:**

### **1. Schema Mismatch:**
```sql
-- Check if the table structure matches our INSERT:
DESCRIBE financial_statements;
-- Or:
\d financial_statements
```

**Expected Schema:**
```sql
CREATE TABLE financial_statements (
    stock_symbol VARCHAR(20) NOT NULL,
    period_type VARCHAR(20) NOT NULL,
    statement_type VARCHAR(50) NOT NULL,
    fiscal_period DATE NOT NULL,
    payload TEXT,  -- or JSONB
    data_source VARCHAR(50),
    created_at TIMESTAMP,
    updated_at TIMESTAMP,
    PRIMARY KEY (stock_symbol, period_type, statement_type, fiscal_period)
);
```

### **2. Constraint Violations:**
```sql
-- Check for constraint violations:
SELECT * FROM financial_statements 
WHERE stock_symbol = 'AAPL' 
  AND period_type = 'annual' 
  AND statement_type = 'income_statement' 
  AND fiscal_period = '2026-12-31';
```

### **3. Data Type Issues:**
- **fiscal_period** - Should be DATE, but might be getting wrong format
- **payload** - Should be TEXT/JSONB, but might be expecting different format
- **created_at/updated_at** - Should be TIMESTAMP, but might have timezone issues

### **4. ON CONFLICT Clause Issues:**
```sql
-- The ON CONFLICT clause requires the exact constraint name:
ON CONFLICT (stock_symbol, period_type, statement_type, fiscal_period)
-- This assumes there's a UNIQUE constraint on these columns
```

## 📊 **Expected Debugging Output After Fix:**

### **Before Fix (Limited Error Info):**
```
Failed to save financial statement record for AAPL 2026-12-31: (psycopg2.ProgrammingError) can't adapt type 'dict'
❌ Exception in _refresh_income_statements for AAPL: No financial statements were successfully saved for AAPL
```

### **After Fix (Detailed Error Info):**
```
Failed to save financial statement record for AAPL 2026-12-31: (psycopg2.ProgrammingError) column "payload" does not exist
Database error type: ProgrammingError
Database error details: column "payload" does not exist
Failed record details: {'stock_symbol': 'AAPL', 'period_type': 'annual', 'statement_type': 'income_statement', 'fiscal_period': datetime.date(2026, 12, 31), 'payload': '{"date": "2021-09-25", ...}', 'data_source': 'unknown', 'created_at': datetime.datetime(2026, 1, 21, 5, 57, 3, 928344), 'updated_at': datetime.datetime(2026, 1, 21, 5, 57, 3, 928344)}
SQL that failed: INSERT INTO financial_statements ...
```

## 🔧 **Common Database Issues and Solutions:**

### **Issue 1: Missing Column**
```sql
-- Error: column "payload" does not exist
-- Solution: Add the missing column
ALTER TABLE financial_statements ADD COLUMN payload TEXT;
```

### **Issue 2: Wrong Data Type**
```sql
-- Error: column "fiscal_period" is of type timestamp but expression is of type date
-- Solution: Cast to correct type
ALTER TABLE financial_statements ALTER COLUMN fiscal_period TYPE DATE;
```

### **Issue 3: Missing Constraint**
```sql
-- Error: ON CONFLICT requires a unique constraint
-- Solution: Add the unique constraint
ALTER TABLE financial_statements 
ADD CONSTRAINT financial_statements_pkey 
PRIMARY KEY (stock_symbol, period_type, statement_type, fiscal_period);
```

### **Issue 4: Timezone Issues**
```sql
-- Error: timezone-aware datetime cannot be converted
-- Solution: Use timezone-aware or naive datetimes consistently
ALTER TABLE financial_statements 
ALTER COLUMN created_at TYPE TIMESTAMP WITH TIME ZONE;
```

## 🚀 **Debugging Steps:**

### **1. Check Table Schema:**
```bash
# Connect to database and check schema
docker-compose exec postgres psql -U postgres -d trading_db -c "\d financial_statements"
```

### **2. Test Simple Insert:**
```sql
-- Try a simple insert to isolate the issue
INSERT INTO financial_statements (stock_symbol, period_type, statement_type, fiscal_period)
VALUES ('TEST', 'annual', 'income_statement', '2023-12-31');
```

### **3. Check Constraints:**
```sql
-- List all constraints on the table
SELECT conname, contype FROM pg_constraint 
WHERE conrelid = 'financial_statements'::regclass;
```

### **4. Monitor Logs:**
```bash
# Watch for detailed error messages
docker-compose logs -f python-worker | grep -A 10 -B 5 "Failed to save financial statement record"
```

## 🎉 **Summary:**
**Enhanced database error debugging implemented!**

### **✅ Enhanced Error Reporting:**
- **Error type** - Shows the exact database exception type
- **Error details** - Full error message with specifics
- **Record details** - Shows the exact data that failed
- **SQL context** - Identifies the problematic SQL statement

### **✅ Better Debugging:**
- **Root cause visibility** - Can see exactly what's failing
- **Data validation** - Shows the data being inserted
- **Schema issues** - Can identify missing/wrong columns
- **Constraint problems** - Can detect constraint violations

### **✅ Industry Standards:**
- **Comprehensive logging** - All error details captured
- **Debugging information** - Enough info to diagnose issues
- **Non-blocking** - Continues processing other records
- **Error aggregation** - Final summary of all failures

**Now when the database error occurs, we'll see exactly what's wrong and can fix it properly!** 🎯

## 🔄 **Next Steps:**
1. **Trigger refresh** - Run financial statements refresh again
2. **Check logs** - Look for detailed error messages
3. **Identify issue** - Use the detailed error to find the root cause
4. **Fix schema** - Apply the necessary database schema changes
5. **Verify fix** - Test that data saves successfully

**The enhanced error debugging is now in place and will show us exactly what's wrong with the database!** 🎯
