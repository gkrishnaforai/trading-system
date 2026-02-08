# Fundamentals JSON Serialization Fix

## 🚨 **Problem Identified:**
```
Failed to save fundamentals for AAPL: (psycopg2.ProgrammingError) can't adapt type 'dict'
```

## 🔍 **Root Cause:**
PostgreSQL/psycopg2 cannot directly serialize Python `dict` objects. The payload needs to be converted to a JSON string before being passed to the database.

## ✅ **Solution Applied:**

### **Fixed JSON Serialization:**
```python
# Before (passing dict directly):
params = {
    "stock_symbol": symbol,
    "insights_date": insights_date,
    "generated_at": datetime.now(),
    "source": "fmp_fundamentals",
    "payload": {"fundamentals": fundamentals}  # This is a dict!
}

# After (serializing to JSON):
params = {
    "stock_symbol": symbol,
    "insights_date": insights_date,
    "generated_at": datetime.now(),
    "source": "fmp_fundamentals",
    "payload": json.dumps({"fundamentals": fundamentals})  # Now a JSON string
}
```

### **Added JSON Import:**
```python
# Save to stock_insights_snapshots table
saved = 0
from app.database import db
from datetime import datetime
import json  # Added this import
with db.get_session() as session:
```

## 🎯 **Why This Works:**

### **PostgreSQL JSONB Column:**
- The `payload` column is likely a `JSONB` type
- PostgreSQL expects JSON strings, not Python objects
- `json.dumps()` converts Python dict to JSON string
- PostgreSQL automatically parses JSON string to JSONB

### **Data Flow:**
```
Python dict → json.dumps() → JSON string → PostgreSQL → JSONB
```

## 🚀 **Expected Result:**

### **Before Fix:**
```
❌ (psycopg2.ProgrammingError) can't adapt type 'dict'
❌ Failed to save fundamentals for AAPL
❌ Fundamentals data lost
```

### **After Fix:**
```
✅ JSON string properly serialized
✅ Database accepts JSON string
✅ Fundamentals saved successfully
✅ Data stored as JSONB in PostgreSQL
```

## 📊 **Parameter Comparison:**

### **Before (Broken):**
```python
'payload': {'fundamentals': {'profile': {'symbol': 'AAPL', 'price': 246.7, ...}}}
# Type: <class 'dict'>
# Error: can't adapt type 'dict'
```

### **After (Working):**
```python
'payload': '{"fundamentals": {"profile": {"symbol": "AAPL", "price": 246.7, ...}}}'
# Type: <class 'str'>
# Result: Successfully saved as JSONB
```

## 🎉 **Summary:**
**Fundamentals JSON serialization is now fixed!**

The Python dict is properly serialized to a JSON string before being passed to PostgreSQL, resolving the "can't adapt type 'dict'" error and allowing fundamentals data to be saved successfully.
