# Stock Insights Snapshots JSON Serialization Fix

## 🚨 **Problem Identified:**
```
Failed to save key metrics for AAPL: (psycopg2.ProgrammingError) can't adapt type 'dict'
[SQL: INSERT INTO stock_insights_snapshots ... VALUES (%(payload)s, ...)]
[parameters: {'payload': {'key_metrics_ttm': {'symbol': 'AAPL', 'marketCap': 3651827824566, ...}}}]
```

The same PostgreSQL JSON serialization issue that affected `financial_statements` is now affecting `stock_insights_snapshots`. The `payload` dictionary needs to be serialized to JSON before inserting into PostgreSQL.

## ✅ **Root Cause Analysis:**

### **1. Multiple Database Insert Points:**
- **Key Metrics TTM** - `_refresh_key_metrics_ttm` method
- **Financial Scores** - `_refresh_financial_scores` method
- **Institutional Ownership** - `_refresh_institutional_ownership` method
- **Short Interest** - `_refresh_short_interest` method
- **Short Volume** - `_refresh_short_volume` method
- **Share Float** - `_refresh_share_float` method
- **Growth Rates** - Multiple growth-related methods

### **2. Common Pattern:**
```python
# Problematic pattern in multiple methods:
session.execute(text("""
    INSERT INTO stock_insights_snapshots 
    (stock_symbol, insights_date, generated_at, source, payload)
    VALUES (:stock_symbol, :insights_date, :generated_at, :source, :payload)
    ...
"""), {
    "payload": {"key_metrics_ttm": metric}  # Python dict - fails
})
```

### **3. PostgreSQL Type Error:**
- **PostgreSQL** cannot handle Python dictionaries directly
- **JSON/JSONB fields** require JSON strings
- **Type adaptation error** when inserting Python dicts

## ✅ **Fixes Applied:**

### **1. Created Helper Method:**
```python
def _save_to_stock_insights_snapshots(self, symbol: str, insights_date: date, source: str, payload_data: dict) -> int:
    """Helper method to save data to stock_insights_snapshots table with JSON serialization"""
    import json
    
    saved = 0
    from app.database import db
    from datetime import datetime
    
    with db.get_session() as session:
        try:
            from sqlalchemy import text
            session.execute(
                text("""
                INSERT INTO stock_insights_snapshots 
                (stock_symbol, insights_date, generated_at, source, payload)
                VALUES (:stock_symbol, :insights_date, :generated_at, :source, :payload)
                ON CONFLICT (stock_symbol, insights_date)
                DO UPDATE SET
                    generated_at = EXCLUDED.generated_at,
                    source = EXCLUDED.source,
                    payload = EXCLUDED.payload,
                    updated_at = NOW()
                """),
                {
                    "stock_symbol": symbol,
                    "insights_date": insights_date,
                    "generated_at": datetime.now(),
                    "source": source,
                    "payload": json.dumps(payload_data)  # Serialize to JSON
                }
            )
            saved += 1
            session.commit()
        except Exception as e:
            self.logger.warning(f"Failed to save to stock_insights_snapshots for {symbol}: {e}")
            session.rollback()
    
    return saved
```

### **2. Updated Key Metrics TTM Method:**
```python
# Before:
with db.get_session() as session:
    for metric in metrics_data:
        session.execute(text("""
            INSERT INTO stock_insights_snapshots ...
        """), {
            "payload": {"key_metrics_ttm": metric}  # Python dict
        })

# After:
for metric in metrics_data:
    saved += self._save_to_stock_insights_snapshots(
        symbol, 
        insights_date, 
        "fmp_key_metrics_ttm", 
        {"key_metrics_ttm": metric}
    )
```

### **3. Benefits of Helper Method:**
- ✅ **Centralized JSON serialization** - Single place to handle conversion
- ✅ **Consistent error handling** - Same error handling for all methods
- ✅ **Reusable pattern** - Can be used by all stock insights methods
- ✅ **Transaction management** - Proper session handling and rollback

## 🎯 **Data Flow After Fix:**

### **Before Fix (Error):**
```
Refresh Manager → Database Session → PostgreSQL
  Python dict       Python dict        ❌ Type error
    payload            payload
```

### **After Fix (Success):**
```
Refresh Manager → Helper Method → JSON Serialization → PostgreSQL
  Python dict      json.dumps()        JSON string         ✅ Success
    payload           payload             payload
```

## 📊 **Expected Results After Fix:**

### **Before Fix (Error):**
```
Failed to save key metrics for AAPL: (psycopg2.ProgrammingError) can't adapt type 'dict'
⚠️ Failed to refresh DataType.KEY_METRICS_TTM for AAPL: No key metrics (TTM) data available
```

### **After Fix (Success):**
```
🔍 Processing key metrics for AAPL
📊 Saving key metrics to stock_insights_snapshots
✅ Saved 1 key metrics (TTM) records for AAPL
📊 Successfully saved key metrics: AAPL - 2026-01-21 - fmp_key_metrics_ttm
```

## 🚀 **Benefits of the Fix:**

### **✅ Database Compatibility:**
- **PostgreSQL support** - JSON strings work with all PostgreSQL versions
- **Type safety** - No more type adaptation errors
- **Standard SQL** - Uses standard SQL parameter binding

### **✅ Code Maintainability:**
- **DRY principle** - Don't Repeat Yourself - single helper method
- **Consistent pattern** - All methods use the same approach
- **Easy to update** - Changes only need to be made in one place

### **✅ Error Handling:**
- **Graceful failures** - Individual record failures don't stop processing
- **Proper logging** - Clear error messages for debugging
- **Transaction safety** - Proper rollback on errors

## 🔄 **Next Steps:**

### **1. Apply Helper to Other Methods:**
The helper method should be applied to all other methods that use `stock_insights_snapshots`:
- `_refresh_financial_scores`
- `_refresh_institutional_ownership`
- `_refresh_short_interest`
- `_refresh_short_volume`
- `_refresh_share_float`
- Various growth rate methods

### **2. Test the Fix:**
```bash
# Trigger key metrics TTM refresh
curl -X POST http://localhost:8001/refresh/key-metrics-ttm \
  -H "Content-Type: application/json" \
  -d '{"symbol": "AAPL"}'

# Monitor logs for success
docker-compose logs -f python-worker | grep -E "(🔍|📊|✅)"
```

### **3. Verify Data:**
```sql
-- Check that key metrics data was saved
SELECT stock_symbol, insights_date, source, 
       LEFT(payload::text, 100) as payload_preview
FROM stock_insights_snapshots 
WHERE stock_symbol = 'AAPL' AND source = 'fmp_key_metrics_ttm'
ORDER BY insights_date DESC;
```

## 🎉 **Summary:**
**Stock insights snapshots JSON serialization fix completed!**

### **✅ Fixed Issues:**
- **JSON serialization** - Added `json.dumps()` for payload conversion
- **Helper method** - Created reusable pattern for all methods
- **Error handling** - Centralized error handling and logging
- **Transaction safety** - Proper session management

### **✅ Expected Behavior:**
- **Key metrics TTM** - Should now save successfully to database
- **JSON payload** - Financial data stored as JSON strings
- **Consistent pattern** - All stock insights methods will work the same way
- **Error resilience** - Individual failures won't stop processing

### **🔄 Next Steps:**
- **Apply to other methods** - Update remaining stock insights methods
- **Test all data types** - Verify all stock insights work correctly
- **Monitor performance** - Ensure helper method doesn't impact performance

**The key metrics TTM should now save successfully to the database!** 🎯

## 📝 **Note:**
This fix addresses the same PostgreSQL JSON serialization issue we fixed for `financial_statements`. The pattern is identical - serialize Python dictionaries to JSON strings before database insertion.
