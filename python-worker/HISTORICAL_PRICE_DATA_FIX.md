# Historical Price Data Fix

## 🚨 **Problem Identified:**
```
Error refreshing historical price for AAPL: Empty price data from primary source
ValueError: Empty price data from primary source
```

This is the same issue we fixed for 5-minute intraday data, but now it's happening for historical price data (1y period).

## ✅ **Root Cause Analysis:**

### **1. API Parameter Mismatch:**
- **Refresh Manager** was calling: `fetch_price_data(symbol, period="1y")`
- **FMP Client** was ignoring the `period` parameter for daily data
- **FMP Historical API** expects: `start_date` and `end_date` parameters

### **2. Incomplete Implementation:**
The FMP client's `fetch_price_data` method only handled `interval="5m"` specially, but for daily data (default interval="1d"), it was ignoring the `period` parameter and just calling `get_historical_prices_full(symbol)` which gets all available historical data.

### **3. Data Flow Issue:**
```
Refresh Manager → Composite Source → FMP Client → FMP API
     period="1y"         period="1y"        period="1y" ❌
                                               (ignored)
```

## ✅ **Fix Applied:**

### **Enhanced FMP Client `fetch_price_data` Method:**
```python
def fetch_price_data(self, symbol: str, **kwargs) -> pd.DataFrame:
    """Fetch price data - supports both daily and intraday intervals"""
    interval = kwargs.get("interval", "1d")  # Default to daily
    
    if interval == "5m":
        # Handle 5-minute intraday data (already working)
        ...
    else:
        # Handle daily historical data - NEW IMPLEMENTATION
        period = kwargs.get("period", "1y")  # Default to 1 year
        start_date = kwargs.get("start_date")
        end_date = kwargs.get("end_date")
        
        # Convert period to start_date and end_date if not provided
        if not start_date or not end_date:
            from datetime import datetime, timedelta
            
            end_date = datetime.now().strftime("%Y-%m-%d")
            
            # Parse period (e.g., "1y", "6m", "30d")
            if period.endswith("y"):
                years = int(period[:-1])
                start_date = (datetime.now() - timedelta(days=years*365)).strftime("%Y-%m-%d")
            elif period.endswith("m"):
                months = int(period[:-1])
                start_date = (datetime.now() - timedelta(days=months*30)).strftime("%Y-%m-%d")
            elif period.endswith("d"):
                days = int(period[:-1])
                start_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
            else:
                # Default to 1 year if format not recognized
                start_date = (datetime.now() - timedelta(days=365)).strftime("%Y-%m-%d")
        
        logger.info(f"🔍 Fetching daily historical data for {symbol} from {start_date} to {end_date}")
        hist_data = self.get_historical_prices_full(symbol, start_date, end_date)
        
        if hist_data and "historical" in hist_data:
            logger.info(f"✅ Fetched {len(hist_data['historical'])} daily data points for {symbol}")
            return pd.DataFrame(hist_data["historical"])
        else:
            logger.warning(f"⚠️ No daily historical data returned for {symbol}")
            return pd.DataFrame()
```

## 🎯 **Data Flow After Fix:**
```
Refresh Manager → Composite Source → FMP Client → FMP API
     period="1y"         period="1y"        start_date="2025-01-21" ✅
                                           end_date="2026-01-21"   ✅
```

## 📊 **Expected Results After Fix:**

### **Before Fix (Error):**
```
Error refreshing historical price for AAPL: Empty price data from primary source
ValueError: Empty price data from primary source
❌ Exception in _refresh_data_type_with_result for DataType.PRICE_HISTORICAL
```

### **After Fix (Success):**
```
🔍 Fetching daily historical data for AAPL from 2025-01-21 to 2026-01-21
✅ Fetched 252 daily data points for AAPL
📊 Primary source result for AAPL: <class 'pandas.core.frame.DataFrame'> - Empty: False
✅ Fetched 252 price data rows from primary (fmp) for AAPL
✅ Saved 252 historical price records for AAPL
```

## 🚀 **Benefits of the Fix:**

### **✅ Period Support:**
- **Flexible periods** - Supports "1y", "6m", "30d" formats
- **Date conversion** - Automatically converts period to start/end dates
- **Fallback support** - Uses 1 year default if format not recognized

### **✅ API Compatibility:**
- **Correct parameters** - Uses `start_date`/`end_date` for FMP API
- **Proper date format** - Uses YYYY-MM-DD format expected by FMP
- **Backward compatibility** - Still works with existing daily data calls

### **✅ Enhanced Logging:**
- **Parameter visibility** - Shows exact date range being requested
- **Data flow tracking** - Shows conversion from period to dates
- **Success/failure clarity** - Clear indicators for data fetching

## 🔄 **Supported Period Formats:**

### **✅ Years:**
- `"1y"` → 1 year ago to today
- `"2y"` → 2 years ago to today
- `"5y"` → 5 years ago to today

### **✅ Months:**
- `"1m"` → 1 month ago to today
- `"6m"` → 6 months ago to today
- `"12m"` → 12 months ago to today

### **✅ Days:**
- `"30d"` → 30 days ago to today
- `"90d"` → 90 days ago to today
- `"365d"` → 365 days ago to today

### **✅ Custom Dates:**
- Can also pass `start_date` and `end_date` directly
- Overrides period conversion if both are provided

## 🔄 **Next Steps:**

### **1. Test the Fix:**
```bash
# Trigger historical price refresh
curl -X POST http://localhost:8001/refresh/price-historical \
  -H "Content-Type: application/json" \
  -d '{"symbol": "AAPL"}'

# Monitor logs for success
docker-compose logs -f python-worker | grep -E "(🔍|📊|✅)"
```

### **2. Verify Data:**
```sql
-- Check that historical price data was saved
SELECT symbol, COUNT(*) as record_count, 
       MIN(date) as start_date, 
       MAX(date) as end_date
FROM raw_market_data_daily 
WHERE symbol = 'AAPL'
GROUP BY symbol;
```

### **3. Test Different Periods:**
```bash
# Test different period formats
for period in "1y" "6m" "30d"; do
    echo "Testing period: $period"
    # The refresh manager uses default 1y, but you can test different periods
done
```

## 🎉 **Summary:**
**Historical price data fix completed!**

### **✅ Fixed Issues:**
- **Period parameter support** - Now handles "1y", "6m", "30d" formats
- **Date conversion** - Automatically converts period to start/end dates
- **API compatibility** - Uses correct FMP API parameters
- **Enhanced logging** - Shows date range being requested

### **✅ Expected Behavior:**
- **1-year historical data** - Fetches last 365 days of price data
- **Flexible periods** - Supports various period formats
- **Date range control** - Uses specific start/end dates
- **Consistent pattern** - Same approach as 5m intraday fix

### **🔄 Next Steps:**
- **Test historical refresh** - Verify 1y period works correctly
- **Check data quality** - Ensure price data is saved properly
- **Monitor performance** - Check that date conversion doesn't impact performance

**The historical price data refresh should now work correctly with period parameters!** 🎯
