#!/bin/bash
# Test all API endpoints for advanced analysis tabs
# Usage: ./scripts/test_all_endpoints.sh [SYMBOL]

SYMBOL="${1:-AAPL}"
BASE_URL="http://localhost:8000/api/v1"

echo "🧪 Testing all endpoints for $SYMBOL"
echo "======================================"
echo ""

echo "1️⃣  📊 Moving Averages:"
echo "   curl \"$BASE_URL/stock/$SYMBOL?subscription_level=pro\" | jq '.indicators | {ma7, ma21, sma50, ema20, ema50, sma200}'"
curl -s "$BASE_URL/stock/$SYMBOL?subscription_level=pro" | jq '.indicators | {ma7, ma21, sma50, ema20, ema50, sma200}'
echo ""

echo "2️⃣  📉 MACD & RSI:"
echo "   curl \"$BASE_URL/stock/$SYMBOL?subscription_level=pro\" | jq '.indicators | {macd, macd_signal, macd_histogram, rsi}'"
curl -s "$BASE_URL/stock/$SYMBOL?subscription_level=pro" | jq '.indicators | {macd, macd_signal, macd_histogram, rsi}'
echo ""

echo "3️⃣  📈 Volume:"
echo "   curl \"$BASE_URL/stock/$SYMBOL/advanced-analysis?subscription_level=pro\" | jq '.volume | .[0:3]'"
curl -s "$BASE_URL/stock/$SYMBOL/advanced-analysis?subscription_level=pro" | jq '.volume | .[0:3]'
echo ""

echo "4️⃣  🧮 ATR & Volatility:"
echo "   curl \"$BASE_URL/stock/$SYMBOL/advanced-analysis?subscription_level=pro\" | jq '.atr_volatility'"
curl -s "$BASE_URL/stock/$SYMBOL/advanced-analysis?subscription_level=pro" | jq '.atr_volatility'
echo ""

echo "5️⃣  🧠 AI Narrative:"
echo "   curl \"$BASE_URL/llm_blog/$SYMBOL\" | jq '.content // .message'"
curl -s "$BASE_URL/llm_blog/$SYMBOL" | jq '.content // .message' | head -5
echo ""

echo "6️⃣  📚 Fundamentals:"
echo "   curl \"$BASE_URL/stock/$SYMBOL/fundamentals\" | jq '{market_cap, pe_ratio, sector, industry}'"
curl -s "$BASE_URL/stock/$SYMBOL/fundamentals" | jq '{market_cap, pe_ratio, sector, industry}'
echo ""

echo "7️⃣  📰 News:"
echo "   curl \"$BASE_URL/stock/$SYMBOL/news\" | jq '.news | .[0:2] | .[] | {title, publisher}'"
curl -s "$BASE_URL/stock/$SYMBOL/news" | jq '.news | .[0:2] | .[] | {title, publisher}'
echo ""

echo "8️⃣  💰 Earnings:"
echo "   curl \"$BASE_URL/stock/$SYMBOL/earnings\" | jq '.earnings | .[0:2]'"
curl -s "$BASE_URL/stock/$SYMBOL/earnings" | jq '.earnings | .[0:2]'
echo ""

echo "9️⃣  🏭 Industry & Peers:"
echo "   curl \"$BASE_URL/stock/$SYMBOL/industry-peers\" | jq '{sector, industry, peer_count: (.peers | length)}'"
curl -s "$BASE_URL/stock/$SYMBOL/industry-peers" | jq '{sector, industry, peer_count: (.peers | length)}'
echo ""

echo "🔟 📊 Comprehensive Advanced Analysis:"
echo "   curl \"$BASE_URL/stock/$SYMBOL/advanced-analysis?subscription_level=pro\" | jq '{symbol, data_available, moving_averages, macd, rsi}'"
curl -s "$BASE_URL/stock/$SYMBOL/advanced-analysis?subscription_level=pro" | jq '{symbol, data_available, moving_averages, macd, rsi}'
echo ""

echo "✅ Testing complete!"

