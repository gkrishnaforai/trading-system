# Streamlit UI API Debugging Guide

## 🔍 Problem Analysis

### **What Works:**
✅ **Direct API calls** work perfectly:
```bash
curl -X POST http://127.0.0.1:8001/signal/tqqq \
  -H "Content-Type: application/json" \
  -d '{"date": "2025-05-21"}'

# Returns: {"success": true, "data": {...}}
```

✅ **API with null date** works:
```bash
curl -X POST http://127.0.0.1:8001/signal/tqqq \
  -H "Content-Type: application/json" \
  -d '{"date": null}'

# Returns: {"success": true, "data": {...}}
```

### **What Fails:**
❌ **Streamlit UI** shows error: `fetch_market_data_for_comparison is not defined`

## 🔧 Debugging Steps Implemented

### **1. Added Comprehensive Debugging**
```python
# Debug: Show what we're about to do
st.write(f"🔍 Debug: Getting signals for {symbol}")

# Debug: API call details
st.write(f"🔍 Debug: Calling TQQQ API at {tqqq_api_url}")
st.write(f"🔍 Debug: Payload = {tqqq_payload}")

# Debug: Response details
st.write(f"🔍 Debug: TQQQ Response status = {tqqq_response.status_code}")
st.write(f"🔍 Debug: Response = {tqqq_response.text}")
```

### **2. Enhanced Error Handling**
```python
try:
    tqqq_response = requests.post(tqqq_api_url, json=tqqq_payload, timeout=5)
    if tqqq_response.status_code == 200:
        signals_data['tqqq_engine'] = tqqq_response.json()
        st.write(f"🔍 Debug: TQQQ API success!")
    else:
        st.write(f"🔍 Debug: TQQQ API failed with status {tqqq_response.status_code}")
        st.write(f"🔍 Debug: Response = {tqqq_response.text}")
        
except Exception as e:
    st.error(f"🔍 Debug: TQQQ engine error: {str(e)}")
    st.warning(f"TQQQ engine unavailable: {str(e)}")
```

## 🎯 Potential Root Causes

### **1. Environment Differences**
- **Curl**: Runs in shell environment
- **Streamlit**: Runs in Python environment with different imports
- **Python Path**: Different module resolution

### **2. Import Issues**
- **Missing Function**: `fetch_market_data_for_comparison` exists in dashboard but not API
- **Circular Imports**: Possible import conflicts
- **Module Resolution**: Different import paths in different contexts

### **3. API Endpoint Differences**
- **Direct Call**: Uses exact endpoint
- **Streamlit Call**: Might use different URL or parameters
- **Network Issues**: Different network routing

### **4. Error Source Confusion**
- **Old Error**: Error might be from previous session
- **Different Component**: Error might come from generic engine, not TQQQ
- **Cached Error**: Streamlit might be showing cached error

## 🚀 Testing Strategy

### **Step 1: Run Streamlit with Debugging**
1. Start Streamlit dashboard
2. Load TQQQ symbol
3. Check debug output
4. Identify exact failure point

### **Step 2: Compare API Calls**
```python
# What Streamlit sends:
tqqq_payload = {"date": None}  # Python None

# What curl sends:
{"date": null}  # JSON null
```

### **Step 3: Check Both Engines**
- **TQQQ Engine**: Specialized engine
- **Generic Engine**: Adaptive engine
- **Error Source**: Which engine is actually failing?

### **Step 4: Verify Network**
- **API Server**: Running on 127.0.0.1:8001
- **Firewall**: No blocking
- **Timeout**: 5 seconds sufficient

## 🔍 Debug Output Analysis

### **Expected Debug Output:**
```
🔍 Debug: Getting signals for TQQQ
🔍 Debug: Calling TQQQ API at http://127.0.0.1:8001/signal/tqqq
🔍 Debug: Payload = {'date': None}
🔍 Debug: TQQQ Response status = 200
🔍 Debug: TQQQ API success!
```

### **Error Debug Output:**
```
🔍 Debug: TQQQ engine error: fetch_market_data_for_comparison is not defined
```

## 🛠️ Resolution Steps

### **If Debug Shows API Success:**
- Error is elsewhere in the code
- Check signal processing logic
- Check data formatting

### **If Debug Shows API Failure:**
- Check API server logs
- Verify endpoint accessibility
- Check request format

### **If Debug Shows Import Error:**
- Fix missing function imports
- Resolve circular dependencies
- Check Python path

## 📊 Next Steps

### **1. Run Debug Version**
Start Streamlit and observe debug output to identify exact failure point.

### **2. Isolate the Issue**
- Test with different symbols
- Test with different dates
- Test both engines separately

### **3. Fix Root Cause**
- Add missing imports if needed
- Fix function definitions
- Resolve environment issues

### **4. Remove Debug Code**
Once issue is resolved, clean up debug statements for production.

## 🎯 Expected Outcome

With the debugging in place, we should be able to:
1. **Identify** exact failure point
2. **Understand** difference between curl and Streamlit
3. **Resolve** the `fetch_market_data_for_comparison` error
4. **Restore** full Streamlit functionality

The debugging will show us exactly where the API call is failing and why it differs from the working curl commands.
