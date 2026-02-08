# Financial Ratios Table Schema Fix

## 🚨 **Problem Identified:**
```
Failed to save financial ratio for AAPL 2025-09-27: (psycopg2.errors.UndefinedColumn) column "currency" of relation "financial_ratios" does not exist
LINE 3: ...                     (symbol, fiscal_date_ending, currency, ...
```

The SQL statement was trying to insert into columns that don't exist in the actual `financial_ratios` table.

## ✅ **Table Schema Analysis:**

### **Actual financial_ratios Table Structure:**
```sql
Column         |           Type           | Nullable
----------------+--------------------------+----------
id              | bigint                   | not null
symbol         | character varying(10)    | not null
fiscal_date_ending | date               | not null
roe             | numeric(10,4)            | 
roa             | numeric(10,4)            | 
roic            | numeric(10,4)            | 
debt_to_equity  | numeric(10,4)            | 
current_ratio   | numeric(10,4)            | 
receivables_turnover | numeric(10,4)      | 
days_sales_outstanding | numeric(10,4)    | 
return_on_assets | numeric(10,4)           | 
return_on_capital | numeric(10,4)          | 
gross_profit_margin | numeric(10,4)       | 
operating_margin | numeric(10,4)           | 
net_profit_margin | numeric(10,4)          | 
data_source     | character varying(50)    | 
created_at      | timestamp with time zone | 
updated_at      | timestamp with time zone | 
```

### **Missing Columns in SQL:**
- ❌ `currency` - Doesn't exist
- ❌ `pe_ratio` - Doesn't exist  
- ❌ `pb_ratio` - Doesn't exist
- ❌ `quick_ratio` - Doesn't exist

### **Available Columns We Can Use:**
- ✅ `symbol` - Stock symbol
- ✅ `fiscal_date_ending` - Date
- ✅ `roe` - Return on Equity
- ✅ `debt_to_equity` - Debt to Equity Ratio
- ✅ `current_ratio` - Current Ratio
- ✅ `data_source` - Data source identifier

## ✅ **Fix Applied:**

### **1. Updated Field Mapping:**
```python
# Before (trying to use non-existent columns):
db_record = {
    "symbol": symbol,
    "fiscal_date_ending": fiscal_date_obj,
    "currency": ratio.get("currency", "USD"),        # ❌ Doesn't exist
    "pe_ratio": ratio.get("priceEarningsRatio"),    # ❌ Doesn't exist
    "pb_ratio": ratio.get("priceToBookRatio"),      # ❌ Doesn't exist
    "debt_to_equity": ratio.get("debtToEquity"),
    "roe": ratio.get("returnOnEquity"),
    "current_ratio": ratio.get("currentRatio"),
    "quick_ratio": ratio.get("quickRatio"),         # ❌ Doesn't exist
    "data_source": "fmp",
}

# After (using only existing columns):
db_record = {
    "symbol": symbol,
    "fiscal_date_ending": fiscal_date_obj,
    "roe": ratio.get("returnOnEquity"),
    "debt_to_equity": ratio.get("debtToEquity"),
    "current_ratio": ratio.get("currentRatio"),
    "data_source": "fmp",
}
```

### **2. Updated SQL Statement:**
```sql
-- Before (trying to insert into non-existent columns):
INSERT INTO financial_ratios 
(symbol, fiscal_date_ending, currency, pe_ratio, pb_ratio, debt_to_equity, roe, current_ratio, quick_ratio, data_source)
VALUES (:symbol, :fiscal_date_ending, :currency, :pe_ratio, :pb_ratio, :debt_to_equity, :roe, :current_ratio, :quick_ratio, :data_source)

-- After (using only existing columns):
INSERT INTO financial_ratios 
(symbol, fiscal_date_ending, roe, debt_to_equity, current_ratio, data_source)
VALUES (:symbol, :fiscal_date_ending, :roe, :debt_to_equity, :current_ratio, :data_source)
```

### **3. Updated ON CONFLICT Clause:**
```sql
-- Before (referencing non-existent columns):
DO UPDATE SET
    currency = EXCLUDED.currency,
    pe_ratio = EXCLUDED.pe_ratio,
    pb_ratio = EXCLUDED.pb_ratio,
    debt_to_equity = EXCLUDED.debt_to_equity,
    roe = EXCLUDED.roe,
    current_ratio = EXCLUDED.current_ratio,
    quick_ratio = EXCLUDED.quick_ratio,
    updated_at = NOW()

-- After (using only existing columns):
DO UPDATE SET
    roe = EXCLUDED.roe,
    debt_to_equity = EXCLUDED.debt_to_equity,
    current_ratio = EXCLUDED.current_ratio,
    updated_at = NOW()
```

## 🎯 **FMP Data Mapping:**

### **Available FMP Fields → Database Columns:**
```python
"returnOnEquity" → "roe"
"debtToEquity" → "debt_to_equity"  
"currentRatio" → "current_ratio"
```

### **Unused FMP Fields (No matching columns):**
```python
"priceEarningsRatio" → No column (pe_ratio doesn't exist)
"priceToBookRatio" → No column (pb_ratio doesn't exist)
"quickRatio" → No column (quick_ratio doesn't exist)
"currency" → No column (currency doesn't exist)
```

## 🚀 **Expected Result:**

### **Before Fix:**
```
❌ UndefinedColumn: column "currency" of relation "financial_ratios" does not exist
❌ Financial ratios refresh fails completely
```

### **After Fix:**
```
✅ Financial ratios saved successfully
✅ Only available fields are stored
✅ No more column errors
```

## 📊 **Data Storage After Fix:**

### **What Gets Stored:**
- ✅ `symbol` - AAPL
- ✅ `fiscal_date_ending` - 2025-09-27
- ✅ `roe` - Return on Equity value
- ✅ `debt_to_equity` - Debt to Equity ratio
- ✅ `current_ratio` - Current ratio
- ✅ `data_source` - fmp

### **What Gets Ignored:**
- ❌ `pe_ratio` - No column to store
- ❌ `pb_ratio` - No column to store
- ❌ `quick_ratio` - No column to store
- ❌ `currency` - No column to store

## 🎉 **Summary:**
**Financial ratios table schema mismatch fixed!**

The SQL statement now matches the actual table structure:
- ✅ **Only existing columns used** - No more UndefinedColumn errors
- ✅ **Proper field mapping** - FMP data mapped to correct database columns
- ✅ **Valid SQL statement** - Insert and update operations work correctly

**Financial ratios should now save successfully!** 🎯

## 🔄 **Next Steps:**
1. **Restart Python worker** to pick up the SQL fix
2. **Test financial ratios refresh** - should work now
3. **Monitor logs** - should see successful saves
4. **Verify database records** - check financial_ratios table

**The UndefinedColumn error should be completely resolved!** 🎯
