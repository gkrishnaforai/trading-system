#!/bin/bash

# Quick Alert System Test - Essential Flow Only
# Tests: Create -> Collect Data -> Process -> Check Results

API_BASE="http://localhost:8001/api/v1/universal-alerts"
USER_ID="4f8b2cb1-4ed6-4fb5-bd44-48e5acc830a4"

echo "🚀 Quick Alert System Test"
echo "=========================="

# 1. Test API Health
echo "1. Testing API Health..."
curl -s "$API_BASE/health" | jq '.status'
echo ""

# 2. Create Analyst Grade Alert
echo "2. Creating Analyst Grade Alert..."
GRADE_RESPONSE=$(curl -s -X POST \
  -H "Content-Type: application/json" \
  -d '{
    "alert_name": "Quick Test Grade Alert",
    "alert_type": "grade_change",
    "entity_filters": {"symbols": ["AAPL", "MSFT"]},
    "event_filters": {
      "data_sources": ["fmp"],
      "include_upgrades": true,
      "include_downgrades": true
    },
    "notification_config": {"channels": ["email"]},
    "priority_level": 3,
    "is_test": true
  }' \
  "$API_BASE/alerts?user_id=$USER_ID")

GRADE_ALERT_ID=$(echo "$GRADE_RESPONSE" | jq -r '.alert_id')
echo "Grade Alert ID: $GRADE_ALERT_ID"
echo ""

# 3. Create Earnings Alert
echo "3. Creating Earnings Alert..."
EARNINGS_RESPONSE=$(curl -s -X POST \
  -H "Content-Type: application/json" \
  -d '{
    "alert_name": "Quick Test Earnings Alert",
    "alert_type": "earnings",
    "entity_filters": {"symbols": ["AAPL", "GOOGL"]},
    "event_filters": {
      "data_sources": ["fmp"],
      "min_days_ahead": 7,
      "max_days_ahead": 1
    },
    "notification_config": {"channels": ["email"]},
    "priority_level": 2,
    "is_test": true
  }' \
  "$API_BASE/alerts?user_id=$USER_ID")

EARNINGS_ALERT_ID=$(echo "$EARNINGS_RESPONSE" | jq -r '.alert_id')
echo "Earnings Alert ID: $EARNINGS_ALERT_ID"
echo ""

# 4. List Alerts
echo "4. Listing User Alerts..."
curl -s "$API_BASE/alerts?user_id=$USER_ID" | jq '.alerts[] | {alert_id, alert_name, alert_type, is_active}'
echo ""

# 5. Collect Analyst Grades Data
echo "5. Collecting Analyst Grades Data..."
curl -s "http://localhost:8001/api/v1/grades/latest" | jq '.'
echo ""

# 6. Collect Earnings Data
echo "6. Collecting Earnings Data..."
# Note: Using existing earnings calendar endpoint
curl -s "http://localhost:8001/admin/earnings-calendar" | jq '.'
echo ""

# 7. Process Events
echo "7. Processing Events..."
# Create a test event to trigger alerts
curl -s -X POST \
  -H "Content-Type: application/json" \
  -d '{
    "event_type": "grade_change",
    "entity_type": "stock",
    "entity_id": "AAPL",
    "event_data": {
      "symbol": "AAPL",
      "old_grade": "Hold",
      "new_grade": "Buy",
      "grading_company": "Test Firm",
      "grade_date": "2026-01-18"
    }
  }' \
  "$API_BASE/events" | jq '.'
echo ""

# 8. Check Alert Status
echo "8. Checking Alert Status..."
if [ "$GRADE_ALERT_ID" != "null" ]; then
    echo "Grade Alert Status:"
    curl -s "$API_BASE/alerts/$GRADE_ALERT_ID?user_id=$USER_ID" | jq '{alert_id, trigger_count, last_triggered_at, is_active}'
fi

if [ "$EARNINGS_ALERT_ID" != "null" ]; then
    echo "Earnings Alert Status:"
    curl -s "$API_BASE/alerts/$EARNINGS_ALERT_ID?user_id=$USER_ID" | jq '{alert_id, trigger_count, last_triggered_at, is_active}'
fi
echo ""

# 9. Check System Health
echo "9. Checking System Health..."
curl -s "$API_BASE/health" | jq '.'
echo ""

# 10. Get System Metrics
echo "10. Getting System Metrics..."
curl -s "$API_BASE/metrics" | jq '.'
echo ""

# 11. Get Alert Statistics
echo "11. Getting Alert Statistics..."
curl -s "$API_BASE/statistics?user_id=$USER_ID&days=1" | jq '.'
echo ""

# 12. Cleanup (optional)
echo "12. Cleanup Test Alerts..."
if [ "$GRADE_ALERT_ID" != "null" ]; then
    curl -s -X DELETE "$API_BASE/alerts/$GRADE_ALERT_ID?user_id=$USER_ID" | jq '.success'
fi

if [ "$EARNINGS_ALERT_ID" != "null" ]; then
    curl -s -X DELETE "$API_BASE/alerts/$EARNINGS_ALERT_ID?user_id=$USER_ID" | jq '.success'
fi

echo ""
echo "✅ Quick Test Complete!"
