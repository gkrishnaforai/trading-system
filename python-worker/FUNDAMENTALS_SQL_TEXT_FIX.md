# Fundamentals SQL Text Expression Fix

## 🚨 **Problem Identified:**
```
Textual SQL expression should be explicitly declared as text()
Failed to save fundamentals for AAPL: Textual SQL expression '\n                        ...' should be explicitly declared as text('\n                        ...')
```

## 🔍 **Root Cause:**
SQLAlchemy requires raw SQL strings to be wrapped with `text()` when using `session.execute()`.

## ✅ **Solution Applied:**

### **Fixed SQL Execution:**
```python
# Before (missing text() wrapper):
session.execute(
    """
    INSERT INTO stock_insights_snapshots 
    (stock_symbol, insights_date, generated_at, source, payload)
    VALUES (:stock_symbol, :insights_date, :generated_at, :source, :payload)
    ON CONFLICT (stock_symbol, insights_date)
    DO UPDATE SET
        generated_at = EXCLUDED.generated_at,
        source = EXCLUDED.source,
        payload = EXCLUDED.payload,
        updated_at = NOW()
    """,
    params
)

# After (with text() wrapper and logging):
from sqlalchemy import text

sql_query = """
    INSERT INTO stock_insights_snapshots 
    (stock_symbol, insights_date, generated_at, source, payload)
    VALUES (:stock_symbol, :insights_date, :generated_at, :source, :payload)
    ON CONFLICT (stock_symbol, insights_date)
    DO UPDATE SET
        generated_at = EXCLUDED.generated_at,
        source = EXCLUDED.source,
        payload = EXCLUDED.payload,
        updated_at = NOW()
    """

# Log the full query for debugging
self.logger.info(f"Executing fundamentals SQL for {symbol}:\n{sql_query}")
self.logger.info(f"SQL Parameters: {params}")

session.execute(text(sql_query), params)
```

## 🎯 **Benefits:**

### **1. SQL Compliance:**
- ✅ Raw SQL properly wrapped with `text()`
- ✅ SQLAlchemy compatibility restored
- ✅ No more "should be explicitly declared as text" errors

### **2. Enhanced Debugging:**
- ✅ Full SQL query logged before execution
- ✅ SQL parameters logged for debugging
- ✅ Easy to test queries in browser/DB client

### **3. Query Testing:**
Now you can copy the logged query and test it directly:

```sql
-- Test in PostgreSQL client:
INSERT INTO stock_insights_snapshots 
(stock_symbol, insights_date, generated_at, source, payload)
VALUES ('AAPL', '2026-01-20', '2026-01-20 19:30:00', 'fmp_fundamentals', '{"fundamentals": {...}}')
ON CONFLICT (stock_symbol, insights_date)
DO UPDATE SET
    generated_at = EXCLUDED.generated_at,
    source = EXCLUDED.source,
    payload = EXCLUDED.payload,
    updated_at = NOW();
```

## 🚀 **Expected Result:**

### **Before Fix:**
```
❌ Textual SQL expression should be explicitly declared as text()
❌ Failed to save fundamentals for AAPL
❌ Fundamentals refresh fails
```

### **After Fix:**
```
✅ SQL query properly executed with text() wrapper
✅ Full query logged for debugging
✅ Fundamentals save successfully
✅ Can test query in browser/DB client
```

## 📊 **Log Output:**
The fix will now log:
```
Executing fundamentals SQL for AAPL:
    INSERT INTO stock_insights_snapshots 
    (stock_symbol, insights_date, generated_at, source, payload)
    VALUES (:stock_symbol, :insights_date, :generated_at, :source, :payload)
    ON CONFLICT (stock_symbol, insights_date)
    DO UPDATE SET
        generated_at = EXCLUDED.generated_at,
        source = EXCLUDED.source,
        payload = EXCLUDED.payload,
        updated_at = NOW()

SQL Parameters: {
    'stock_symbol': 'AAPL',
    'insights_date': datetime.date(2026, 1, 20),
    'generated_at': datetime.datetime(2026, 1, 20, 19, 30),
    'source': 'fmp_fundamentals',
    'payload': {'fundamentals': {...}}
}
```

## 🎉 **Summary:**
**Fundamentals SQL execution is now fixed and debuggable!**

The SQL query is properly wrapped with `text()` and fully logged, allowing you to test the exact query in your browser or database client.
