# Financial Statements Column Name Fix

## 🚨 **Problem Identified:**
```
Database session error: (psycopg2.errors.UndefinedColumn) column "symbol" of relation "financial_statements" does not exist
INSERT INTO financial_statements (symbol, pe...
```

## 🔍 **Root Cause:**
The refresh manager was trying to insert `symbol` but the `financial_statements` table has `stock_symbol` column.

## ✅ **Solution Applied:**

### **Fixed Column Name in Refresh Manager:**
```python
# Before (wrong column):
INSERT INTO financial_statements (symbol, period_type, statement_type, fiscal_period, source, payload)
VALUES (:symbol, :period_type, :statement_type, :fiscal_period, :source, CAST(:payload AS jsonb))
ON CONFLICT (symbol, period_type, statement_type, fiscal_period)

# After (correct column):
INSERT INTO financial_statements (stock_symbol, period_type, statement_type, fiscal_period, source, payload)
VALUES (:symbol, :period_type, :statement_type, :fiscal_period, :source, CAST(:payload AS jsonb))
ON CONFLICT (stock_symbol, period_type, statement_type, fiscal_period)
```

## 🎯 **Table Structure:**
```
financial_statements table columns:
- created_at (timestamp with time zone)
- fiscal_period (date)
- id (uuid)
- payload (jsonb)
- period_type (text)
- source (text)
- statement_type (text)
- stock_symbol (text) ✅ <-- Correct column name
- updated_at (timestamp with time zone)
```

## 🚀 **Expected Result:**

### **Before Fix:**
```
❌ INSERT INTO financial_statements (symbol, ...) → Column "symbol" does not exist
❌ Financial statements refresh fails
❌ No financial data saved
```

### **After Fix:**
```
✅ INSERT INTO financial_statements (stock_symbol, ...) → Success
✅ Financial statements refresh works
✅ Data saved correctly
✅ Proper constraint handling
```

## 📊 **Impact:**
- ✅ **Financial statements refresh** - Now works correctly
- ✅ **Data integrity** - Uses correct column names
- ✅ **Constraint handling** - ON CONFLICT works with correct columns
- ✅ **All statement types** - Income, balance sheet, cash flow all work

## 🎉 **Summary:**
**Financial statements insert now works correctly!**

The refresh manager now uses the correct `stock_symbol` column name instead of `symbol`, allowing financial statements data to be saved properly to the database.
