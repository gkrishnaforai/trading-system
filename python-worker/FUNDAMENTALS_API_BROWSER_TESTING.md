# Fundamentals API Details for Browser Testing

## 🌐 **API Being Used:**
**Financial Modeling Prep (FMP) API**

### **Base URL:**
```
https://financialmodelingprep.com/stable
```

### **Authentication:**
- **Header:** `X-API-KEY` or query parameter `apikey`
- **API Key:** Check your `.env` file for `ALPHA_VANTAGE_API_KEY` or `FMP_API_KEY`

## 📊 **Fundamentals API Endpoints:**

### **1. Company Profile:**
```
GET https://financialmodelingprep.com/stable/profile?symbol=AAPL&apikey=YOUR_API_KEY
```

### **2. Income Statement:**
```
GET https://financialmodelingprep.com/stable/income-statement?symbol=AAPL&period=quarter&apikey=YOUR_API_KEY
```

### **3. Balance Sheet:**
```
GET https://financialmodelingprep.com/stable/balance-sheet-statement?symbol=AAPL&period=quarter&apikey=YOUR_API_KEY
```

### **4. Cash Flow:**
```
GET https://financialmodelingprep.com/stable/cash-flow-statement?symbol=AAPL&period=quarter&apikey=YOUR_API_KEY
```

### **5. Key Metrics:**
```
GET https://financialmodelingprep.com/stable/key-metrics-ttm?symbol=AAPL&apikey=YOUR_API_KEY
```

### **6. Financial Ratios:**
```
GET https://financialmodelingprep.com/stable/ratios-ttm?symbol=AAPL&apikey=YOUR_API_KEY
```

### **7. Financial Scores:**
```
GET https://financialmodelingprep.com/stable/financial-score?symbol=AAPL&apikey=YOUR_API_KEY
```

### **8. Ratings:**
```
GET https://financialmodelingprep.com/stable/rating?symbol=AAPL&apikey=YOUR_API_KEY
```

### **9. Price Targets:**
```
GET https://financialmodelingprep.com/stable/price-target-consensus?symbol=AAPL&apikey=YOUR_API_KEY
```

### **10. Stock Grades:**
```
GET https://financialmodelingprep.com/stable/grade?symbol=AAPL&apikey=YOUR_API_KEY
```

## 🧪 **Browser Testing Steps:**

### **1. Test Basic Company Profile:**
```
https://financialmodelingprep.com/stable/profile?symbol=AAPL&apikey=YOUR_API_KEY
```

### **2. Test Comprehensive Data:**
The system calls multiple endpoints and combines them. Test each one individually.

### **3. Check API Key Validity:**
```
https://financialmodelingprep.com/stable/profile?symbol=AAPL&apikey=YOUR_API_KEY
```

## 🔍 **Expected Response Format:**

### **Company Profile Response:**
```json
[
  {
    "symbol": "AAPL",
    "price": 246.7,
    "beta": 1.093,
    "volAvg": 57871822,
    "mktCap": 3645326078859,
    "lastDiv": 1.03,
    "range": "169.21-199.62",
    "changes": -2.31,
    "companyName": "Apple Inc.",
    "currency": "USD",
    "cik": "0000320193",
    "isin": "US0378331005",
    "cusip": "037833100",
    "exchange": "NASDAQ",
    "exchangeShortName": "NASDAQ",
    "industry": "Technology Hardware, Storage & Peripherals",
    "website": "https://www.apple.com",
    "description": "Apple Inc. designs, manufactures...",
    "sector": "Technology",
    "country": "US",
    "fullTimeEmployees": 164000,
    "phone": "408 996 1010",
    "address": "One Apple Park Way",
    "city": "Cupertino",
    "state": "CA",
    "zip": "95014",
    "dcfDiff": 23.4321,
    "dcf": 223.268,
    "image": "https://financialmodelingprep.com/image-stock/AAPL.png",
    "ipoDate": "1980-12-12",
    "defaultImage": false,
    "isEtf": false,
    "isActivelyTrading": true
  }
]
```

## 🚨 **Common Issues:**

### **1. API Key Problems:**
- **Invalid API Key:** `{"error": "Invalid API key"}`
- **Missing API Key:** `{"error": "API key is required"}`

### **2. Rate Limiting:**
- **Rate Limited:** `{"error": "Rate limit exceeded"}`

### **3. Symbol Not Found:**
- **Invalid Symbol:** `[]` (empty array)

### **4. Network Issues:**
- **Timeout:** No response
- **CORS:** Browser blocks request

## 🛠 **Debugging Steps:**

### **1. Check API Key:**
```bash
# Check your .env file
cat .env | grep -i api
```

### **2. Test Simple Endpoint:**
```
https://financialmodelingprep.com/stable/profile?symbol=AAPL&apikey=YOUR_ACTUAL_API_KEY
```

### **3. Test Different Symbol:**
```
https://financialmodelingprep.com/stable/profile?symbol=MSFT&apikey=YOUR_API_KEY
```

### **4. Check Response Headers:**
Look for rate limiting headers in browser dev tools.

## 📊 **System Integration:**

### **Data Flow:**
1. **Composite Source** tries **FMP** first
2. If FMP fails, falls back to **Yahoo Finance**
3. Combines all endpoints into comprehensive data
4. Stores as JSON in `stock_insights_snapshots` table

### **Error Handling:**
- If all endpoints return empty, system reports "No fundamental data available"
- If any endpoint fails, logs error but continues with others

## 🎯 **Quick Test:**
Copy this URL into your browser (replace YOUR_API_KEY):
```
https://financialmodelingprep.com/stable/profile?symbol=AAPL&apikey=YOUR_API_KEY
```

This will tell you immediately if the API key is working and if the endpoint is returning data!
