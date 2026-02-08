#!/bin/bash

echo "🔄 Restarting Python Worker Server..."

# Kill existing server
pkill -f "start_api_server.py" || true
pkill -f "uvicorn" || true

# Wait a moment
sleep 2

echo "🚀 Starting Python Worker Server..."
cd /Users/krishnag/tools/trading-system/python-worker

# Start server in background
python start_api_server.py > server.log 2>&1 &
SERVER_PID=$!

echo "Server PID: $SERVER_PID"

# Wait for server to start
echo "⏳ Waiting for server to start..."
for i in {1..30}; do
    if curl -s http://127.0.0.1:8001/health > /dev/null 2>&1; then
        echo "✅ Server is ready!"
        break
    fi
    echo "   Waiting... ($i/30)"
    sleep 1
done

# Test the fixes
echo ""
echo "🧪 Testing Fixes..."
echo ""

# Test stocks API format
echo "1. Testing stocks API format..."
STOCKS_RESPONSE=$(curl -s http://127.0.0.1:8001/api/v1/stocks/available)
if echo "$STOCKS_RESPONSE" | grep -q '"success"'; then
    echo "✅ Stocks API returns correct format"
else
    echo "❌ Stocks API still returns raw list"
fi

# Test problematic tables
echo ""
echo "2. Testing problematic tables..."
for table in data_ingestion_events share_float risk_factors stocks; do
    echo "   Testing $table..."
    RESPONSE=$(curl -s http://127.0.0.1:8001/admin/data-summary/$table)
    if echo "$RESPONSE" | grep -q '"success"'; then
        echo "   ✅ $table works"
    else
        echo "   ❌ $table failed"
    fi
done

# Test removed tables
echo ""
echo "3. Testing removed tables..."
for table in weekly_aggregation growth_calculations; do
    echo "   Testing $table..."
    STATUS_CODE=$(curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8001/admin/data-summary/$table)
    if [ "$STATUS_CODE" = "400" ]; then
        echo "   ✅ $table correctly returns 400"
    else
        echo "   ❌ $table returns $STATUS_CODE (should be 400)"
    fi
done

echo ""
echo "📊 Server logs (last 10 lines):"
tail -10 server.log

echo ""
echo "🎯 To stop server: kill $SERVER_PID"
