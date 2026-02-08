# How to Monitor Financial Statements API Calls and Failures

## 🔍 **Monitor Real-Time API Calls:**

### **1. Watch All Financial Statements Activity:**
```bash
# Monitor all financial statements logs with API URLs and responses
docker-compose logs -f python-worker | grep -E "(Financial Statement|📡|📊|❌|⚠️)" --line-buffered
```

### **2. Monitor Specific Symbol:**
```bash
# Monitor only AAPL financial statements
docker-compose logs -f python-worker | grep -A 10 -B 5 "AAPL" | grep -E "(📡|📊|❌|⚠️|Financial)"
```

### **3. Monitor API Calls Only:**
```bash
# See only the FMP API calls with URLs
docker-compose logs -f python-worker | grep "📡 FMP API Call" --line-buffered
```

### **4. Monitor Detailed Exceptions:**
```bash
# See full stack traces and exception details
docker-compose logs -f python-worker | grep -A 20 "❌.*Exception" --line-buffered
```

## 🎯 **What You'll See in the Logs:**

### **📡 API Call Details:**
```
📡 FMP API Call - Income Statement:
   - Endpoint: /income-statement
   - Symbol: AAPL
   - Period: None
   - Full URL: https://financialmodelingprep.com/stable/income-statement?symbol=AAPL
```

### **📊 API Response Details:**
```
📊 FMP Income Statement Response for AAPL:
   - Data type: <class 'list'>
   - Data length: 5
   - Sample keys: ['date', 'symbol', 'revenue', 'netIncome', 'eps']
   - Sample data: {'date': '2025-09-27', 'symbol': 'AAPL', 'revenue': 123456789, ...}
```

### **❌ Exception Details:**
```
❌ Exception refreshing income statements for AAPL: 'FinancialModelingPrepClient' object has no attribute 'base_url'
Traceback (most recent call last):
  File "/app/app/data_management/refresh_manager.py", line 683, in _refresh_data_type_with_result
    rows = self._refresh_income_statements(symbol)
  File "/app/app/providers/financial_modeling_prep/client.py", line 246, in get_income_statement
    logger.info(f"   - Full URL: {self.base_url}{endpoint}?symbol={symbol}")
AttributeError: 'FinancialModelingPrepClient' object has no attribute 'base_url'
```

## 🚀 **Test and Monitor Commands:**

### **1. Trigger Refresh and Monitor:**
```bash
# Terminal 1: Start monitoring
docker-compose logs -f python-worker | grep -E "(📡|📊|❌|⚠️)" --line-buffered

# Terminal 2: Trigger refresh
curl -X POST http://localhost:8001/refresh/income-statements \
  -H "Content-Type: application/json" \
  -d '{"symbol": "AAPL"}'
```

### **2. Test Multiple Data Types:**
```bash
# Trigger all financial statements for AAPL
curl -X POST http://localhost:8001/refresh \
  -H "Content-Type: application/json" \
  -d '{"symbols": ["AAPL"], "data_types": ["income_statements", "balance_sheets", "cash_flow_statements"]}'
```

### **3. Monitor Composite Source Flow:**
```bash
# See data flow through composite source
docker-compose logs -f python-worker | grep -A 5 -B 5 "Composite Source"
```

## 📍 **Where Failures Happen - Flow Analysis:**

### **Complete Data Flow:**
```
1. Refresh Manager → _refresh_income_statements()
2. ↓
3. Refresh Manager → _refresh_financial_statements()
4. ↓
5. Composite Source → fetch_financial_statements()
6. ↓
7. FMP Source → fetch_financial_statements()
8. ↓
9. FMP Client → get_income_statement()
10. ↓
11. FMP API Call → https://financialmodelingprep.com/stable/income-statement?symbol=AAPL
```

### **Failure Points We'll See:**
- ✅ **Level 1-3**: Refresh manager exceptions (with stack traces)
- ✅ **Level 4-5**: Composite source fallback behavior
- ✅ **Level 6-7**: Source adapter issues
- ✅ **Level 8-9**: Client API call details (URLs, parameters)
- ✅ **Level 10-11**: FMP API responses and errors

## 🔧 **Debugging Steps:**

### **Step 1: Check API URL Construction:**
```bash
# Look for these log lines:
📡 FMP API Call - Income Statement:
   - Full URL: https://financialmodelingprep.com/stable/income-statement?symbol=AAPL
```

### **Step 2: Check API Response:**
```bash
# Look for these log lines:
📊 FMP Income Statement Response for AAPL:
   - Data type: <class 'list'>
   - Data length: 0  # ← This indicates empty response
```

### **Step 3: Check Exception Details:**
```bash
# Look for these log lines:
❌ Exception refreshing income statements for AAPL: [specific error]
Full exception details for AAPL:
[stack trace]
```

## 🎯 **Common Failure Scenarios:**

### **Scenario 1: API Key Issues**
```
📡 FMP API Call - Income Statement:
   - Full URL: https://financialmodelingprep.com/stable/income-statement?symbol=AAPL

📊 FMP Income Statement Response for AAPL:
   - Data type: <class 'dict'>
   - Data content: {'error': 'Invalid API key'}

❌ Exception refreshing income statements for AAPL: API key invalid
```

### **Scenario 2: URL Construction Issues**
```
❌ Exception refreshing income statements for AAPL: 'FinancialModelingPrepClient' object has no attribute 'base_url'
```

### **Scenario 3: Empty API Responses**
```
📡 FMP API Call - Income Statement:
   - Full URL: https://financialmodelingprep.com/stable/income-statement?symbol=AAPL

📊 FMP Income Statement Response for AAPL:
   - Data type: <class 'list'>
   - Data length: 0

⚠️ No income statement data available for AAPL
```

### **Scenario 4: Network/Timeout Issues**
```
❌ Exception refreshing income statements for AAPL: Timeout
Full exception details for AAPL:
requests.exceptions.Timeout: HTTPSConnectionPool(host='financialmodelingprep.com', port=443): Read timeout
```

## 🚀 **Start Monitoring Now:**

### **Quick Start Command:**
```bash
# This will show you all the API URLs and failure points in real-time
docker-compose logs -f python-worker | grep -E "(📡|📊|❌|⚠️)" --line-buffered
```

Then in another terminal:
```bash
# Trigger a refresh to see the live flow
curl -X POST http://localhost:8001/refresh/income-statements \
  -H "Content-Type: application/json" \
  -d '{"symbol": "AAPL"}'
```

**You'll see exactly what URL is being used and where the failure occurs!** 🎯
