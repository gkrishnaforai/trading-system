# Earnings Data Date Column Fix

## 🚨 **Problem Identified:**
```
Database session error: (psycopg2.errors.UndefinedColumn) column "report_date" does not exist
LINE 5: COUNT(*) FILTER (WHERE DATE(report_date)...
```

## 🔍 **Root Cause:**
The admin API was trying to use `report_date` column for `earnings_data` table, but the actual column is `earnings_date`.

## ✅ **Solution Applied:**

### **Fixed Column Name:**
```python
# Before (wrong column):
elif table == "earnings_data":
    query = f"""
        SELECT 
            COUNT(*) FILTER (WHERE DATE(report_date) = CURRENT_DATE) as today_records,
            MAX(report_date) as last_updated,
        FROM earnings_data
    """

# After (correct column):
elif table == "earnings_data":
    query = f"""
        SELECT 
            COUNT(*) FILTER (WHERE DATE(earnings_date) = CURRENT_DATE) as today_records,
            MAX(earnings_date) as last_updated,
        FROM earnings_data
    """
```

## 🎯 **Table Column Structure:**
```
earnings_data table columns:
- created_at (timestamp with time zone)
- earnings_at (timestamp with time zone)
- earnings_date (date) ✅ <-- This is the correct column
- earnings_id (text)
- earnings_session (text)
- earnings_timezone (text)
- eps_actual (double precision)
- eps_estimate (double precision)
- id (uuid)
- revenue_actual (bigint)
- revenue_estimate (bigint)
- source (text)
- stock_symbol (text)
- surprise_percentage (double precision)
- updated_at (timestamp with time zone)
```

## 🚀 **Expected Result:**

### **Before Fix:**
```
❌ GET /admin/data-summary/earnings_data → 500 Internal Server Error
❌ Column "report_date" does not exist
❌ SQL query fails
```

### **After Fix:**
```
✅ GET /admin/data-summary/earnings_data → 200 OK
✅ Uses correct earnings_date column
✅ Accurate earnings date-based summaries
✅ Today's records based on earnings_date, not created_at
```

## 📊 **Benefits:**
- ✅ **No more SQL errors** - Uses correct column name
- ✅ **Accurate timing** - Shows earnings dates, not insertion dates
- ✅ **Business relevance** - Today's records based on earnings dates
- ✅ **Consistent API** - Same response format as other tables
- ✅ **Better monitoring** - Can track earnings data freshness by earnings date

## 🎉 **Summary:**
**The earnings_data data summary endpoint now works correctly!**

The admin API now uses the correct `earnings_date` column instead of the non-existent `report_date` column, providing accurate earnings-date-based summaries for the earnings_data table.
