# Backtest API Endpoint Fix - Trading Dashboard

## 🐛 Problem Identified

### **Wrong API Endpoints in Backtest Function**
The `run_tqqq_backtest` function in the Trading Dashboard was using different API endpoints than the direct signal APIs we've been working with:

#### **❌ Wrong API (Before):**
```python
# Using admin/signals/generate endpoint
signal_resp = python_client.post(
    "admin/signals/generate",  # ❌ Different from curl commands!
    json_data={
        "symbols": ["TQQQ"],
        "strategy": strategy,
        "backtest_date": test_date.strftime("%Y-%m-%d")
    }
)
```

#### **✅ Correct APIs (Your Curl Commands):**
```bash
# TQQQ specialized engine
curl -X POST http://127.0.0.1:8001/signal/tqqq \
  -H "Content-Type: application/json" \
  -d '{"date": "2025-11-05"}'

# Generic adaptive engine  
curl -X POST http://127.0.0.1:8001/signal/generic \
  -H "Content-Type: application/json" \
  -d '{"symbol": "TQQQ", "date": "2025-05-21"}'
```

## ✅ Solution Implemented

### **Fixed All Three Backtest Modes**

#### **1. Single Date Mode:**
```python
if mode == "Single Date":
    # Use the same APIs as curl commands
    if strategy == "tqqq_swing":
        # Use TQQQ specialized engine
        signal_resp = python_client.post(
            "signal/tqqq",
            json_data={
                "date": test_date.strftime("%Y-%m-%d")
            }
        )
    else:
        # Use generic adaptive engine
        signal_resp = python_client.post(
            "signal/generic",
            json_data={
                "symbol": "TQQQ",
                "date": test_date.strftime("%Y-%m-%d")
            }
        )
```

#### **2. Date Range Mode:**
```python
elif mode == "Date Range":
    for test_date in date_range:
        # Use the same APIs as curl commands
        if strategy == "tqqq_swing":
            signal_resp = python_client.post(
                "signal/tqqq",
                json_data={"date": test_date.strftime("%Y-%m-%d")}
            )
        else:
            signal_resp = python_client.post(
                "signal/generic",
                json_data={
                    "symbol": "TQQQ",
                    "date": test_date.strftime("%Y-%m-%d")
                }
            )
```

#### **3. Quick Test Week Mode:**
```python
else:  # Quick Test Week
    for test_date in date_range:
        # Use the same APIs as curl commands
        if strategy == "tqqq_swing":
            signal_resp = python_client.post(
                "signal/tqqq",
                json_data={"date": test_date.strftime("%Y-%m-%d")}
            )
        else:
            signal_resp = python_client.post(
                "signal/generic",
                json_data={
                    "symbol": "TQQQ",
                    "date": test_date.strftime("%Y-%m-%d")
                }
            )
```

### **Updated Response Handling**

#### **Before (Wrong Response Structure):**
```python
if signal_resp and signal_resp.get("signals"):
    signal_data = signal_resp["signals"][0]  # ❌ Wrong structure
```

#### **After (Correct Response Structure):**
```python
if signal_resp and signal_resp.get("success"):
    signal_data = signal_resp.get("data", {}).get("signal", {})  # ✅ Correct structure
```

## 🎯 What This Fixes

### **API Consistency:**
- **Before**: Backtest used different API than manual testing
- **After**: Backtest uses same APIs as curl commands
- **Result**: Consistent behavior across all interfaces

### **Engine Selection:**
- **TQQQ Strategy**: Uses `/signal/tqqq` (specialized engine)
- **Generic Strategy**: Uses `/signal/generic` (adaptive engine)
- **Result**: Proper engine selection based on strategy

### **Response Structure:**
- **Before**: Expected `signal_resp["signals"][0]`
- **After**: Expects `signal_resp.get("data", {}).get("signal", {})`
- **Result**: Correct data extraction from API responses

## 📊 API Mapping

### **Strategy to API Endpoint Mapping:**
```python
if strategy == "tqqq_swing":
    # → TQQQ Specialized Engine
    # → POST /signal/tqqq
    # → Payload: {"date": "YYYY-MM-DD"}
    
else:
    # → Generic Adaptive Engine  
    # → POST /signal/generic
    # → Payload: {"symbol": "TQQQ", "date": "YYYY-MM-DD"}
```

### **Response Structure Mapping:**
```python
# Both engines return same structure:
{
  "success": true,
  "data": {
    "signal": {
      "signal": "buy/sell/hold",
      "confidence": 0.8,
      "reasoning": [...],
      "metadata": {...}
    },
    "market_data": {...},
    "analysis": {...}
  }
}
```

## 🚀 Benefits

### **For Testing:**
1. **Consistent Results**: Backtest matches manual API calls
2. **Engine Validation**: Same engines in all interfaces
3. **Debugging**: Easier to troubleshoot with consistent APIs
4. **Verification**: Can verify backtest results with curl

### **For Users:**
1. **Predictable Behavior**: Same signals in backtest as manual testing
2. **Engine Choice**: Can choose specialized vs generic engines
3. **Reliable Results**: Consistent signal generation
4. **Trust**: Confidence in backtest accuracy

### **For Development:**
1. **Single Source of Truth**: One set of signal APIs
2. **Easier Maintenance**: Only one API implementation to maintain
3. **Better Testing**: Can test APIs independently
4. **Clean Architecture**: Consistent API usage patterns

## 🔧 Technical Details

### **API Client Usage:**
```python
python_api_url = os.getenv("PYTHON_API_URL", "http://python-worker:8001")
python_client = APIClient(python_api_url, timeout=30)
```

### **Date Formatting:**
```python
test_date.strftime("%Y-%m-%d")  # "2025-05-21"
```

### **Error Handling:**
```python
if signal_resp and signal_resp.get("success"):
    signal_data = signal_resp.get("data", {}).get("signal", {})
else:
    st.error("❌ Failed to generate signal")
```

## ✅ Verification

### **Test Steps:**
1. **Manual Test**: Run curl command for specific date
2. **Backtest Test**: Run backtest for same date and strategy
3. **Compare Results**: Signals should be identical
4. **Verify Both Engines**: Test both tqqq_swing and generic strategies

### **Expected Results:**
```bash
# Manual curl test
curl -X POST http://127.0.0.1:8001/signal/tqqq -d '{"date": "2025-05-21"}'
# → Returns: {"signal": "sell", "confidence": 0.8, ...}

# Backtest test (same date, tqqq_swing strategy)
# → Should return: {"signal": "sell", "confidence": 0.8, ...}
```

## 🎉 Resolution Summary

**Root Cause**: Backtest function was using different API endpoints than manual testing
**Solution**: Updated all backtest modes to use the same signal APIs as curl commands
**Result**: Consistent signal generation across all interfaces

Now the backtest function uses exactly the same APIs as your curl commands, ensuring consistent behavior and results!
