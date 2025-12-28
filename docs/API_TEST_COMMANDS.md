# API Test Commands for Advanced Analysis Tabs

## All Advanced Analysis Endpoints

### 1. 📊 Moving Averages
```bash
curl "http://localhost:8000/api/v1/stock/AAPL?subscription_level=pro" | jq '.indicators | {ma7, ma21, sma50, ema20, ema50, sma200}'
```

### 2. 📉 MACD & RSI
```bash
# MACD
curl "http://localhost:8000/api/v1/stock/AAPL?subscription_level=pro" | jq '.indicators | {macd, macd_signal, macd_histogram, rsi}'

# Or get RSI separately
curl "http://localhost:8000/api/v1/stock/AAPL?subscription_level=pro" | jq '.indicators.rsi'
```

### 3. 📈 Volume
```bash
# Volume data (last 30 days)
curl "http://localhost:8000/api/v1/stock/AAPL/advanced-analysis?subscription_level=pro" | jq '.volume'

# Or get from raw market data
curl "http://localhost:8000/api/v1/stock/AAPL?subscription_level=pro" | jq '.indicators'
```

### 4. 🧮 ATR & Volatility
```bash
curl "http://localhost:8000/api/v1/stock/AAPL/advanced-analysis?subscription_level=pro" | jq '.atr_volatility'
```

### 5. 🧠 AI Narrative
```bash
curl "http://localhost:8000/api/v1/llm_blog/AAPL" | jq
```

### 6. 📚 Fundamentals
```bash
curl "http://localhost:8000/api/v1/stock/AAPL/fundamentals" | jq
```

### 7. 🏭 Industry & Peers
```bash
curl "http://localhost:8000/api/v1/stock/AAPL/industry-peers" | jq
```

## Comprehensive Advanced Analysis (All-in-One)
```bash
curl "http://localhost:8000/api/v1/stock/AAPL/advanced-analysis?subscription_level=pro" | jq
```

## Test All Endpoints at Once
```bash
#!/bin/bash
SYMBOL="AAPL"
BASE_URL="http://localhost:8000/api/v1"

echo "📊 Moving Averages:"
curl -s "$BASE_URL/stock/$SYMBOL?subscription_level=pro" | jq '.indicators | {ma7, ma21, sma50, ema20, ema50, sma200}'

echo -e "\n📉 MACD & RSI:"
curl -s "$BASE_URL/stock/$SYMBOL?subscription_level=pro" | jq '.indicators | {macd, macd_signal, macd_histogram, rsi}'

echo -e "\n📈 Volume:"
curl -s "$BASE_URL/stock/$SYMBOL/advanced-analysis?subscription_level=pro" | jq '.volume | .[0:5]'

echo -e "\n🧮 ATR & Volatility:"
curl -s "$BASE_URL/stock/$SYMBOL/advanced-analysis?subscription_level=pro" | jq '.atr_volatility'

echo -e "\n📚 Fundamentals:"
curl -s "$BASE_URL/stock/$SYMBOL/fundamentals" | jq '{market_cap, pe_ratio, sector, industry}'

echo -e "\n📰 News:"
curl -s "$BASE_URL/stock/$SYMBOL/news" | jq '.news | .[0:3]'

echo -e "\n💰 Earnings:"
curl -s "$BASE_URL/stock/$SYMBOL/earnings" | jq '.earnings | .[0:3]'

echo -e "\n🏭 Industry & Peers:"
curl -s "$BASE_URL/stock/$SYMBOL/industry-peers" | jq '{sector, industry, peers: .peers | .[0:5]}'
```

## Quick Test Script
Save this as `test_all_endpoints.sh`:
```bash
#!/bin/bash
SYMBOL="${1:-AAPL}"
BASE_URL="http://localhost:8000/api/v1"

echo "Testing all endpoints for $SYMBOL..."
echo "======================================"

for endpoint in "stock/$SYMBOL" "stock/$SYMBOL/advanced-analysis" "stock/$SYMBOL/fundamentals" "stock/$SYMBOL/news" "stock/$SYMBOL/earnings" "stock/$SYMBOL/industry-peers" "llm_blog/$SYMBOL"; do
    echo -e "\n🔍 Testing: $endpoint"
    curl -s "$BASE_URL/$endpoint?subscription_level=pro" | jq -r 'if .data_available == false then "❌ No data" elif .error then "❌ Error: \(.error)" else "✅ Success" end'
done
```

