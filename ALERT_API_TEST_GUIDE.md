# Universal Alert System API Test Guide

## Overview
This guide provides comprehensive curl-based tests for the Universal Alert System API, covering the complete workflow from alert creation to notification delivery.

## Prerequisites

1. **Start the Python Worker API Server:**
```bash
cd /Users/krishnag/tools/trading-system/python-worker
source venv/bin/activate
python start_api_server.py
```

2. **Install jq (JSON processor):**
```bash
# macOS
brew install jq

# Ubuntu/Debian
sudo apt-get install jq
```

3. **Verify API is accessible:**
```bash
curl http://localhost:8001/api/v1/universal-alerts/health
```

## Test Scripts

### 1. Comprehensive Test Suite (`test_alert_api_flow.sh`)
**Purpose**: Complete end-to-end testing of all alert system features
**Runtime**: ~2-3 minutes
**Coverage**: Full CRUD operations, data collection, processing, notifications, audit trail

#### Usage:
```bash
./test_alert_api_flow.sh
```

#### Test Flow:
1. **API Connectivity Check** - Verify API is accessible
2. **Create Analyst Grade Alert** - Test grade change alert creation
3. **Create Earnings Calendar Alert** - Test earnings alert creation
4. **List User Alerts** - Verify alerts are stored
5. **Collect Analyst Grades Data** - Trigger data collection for grades
6. **Collect Earnings Calendar Data** - Trigger data collection for earnings
7. **Process Events** - Process collected events through alert engine
8. **Check Alert Status** - Verify alert statistics
9. **Check Notification Queue** - View pending notifications
10. **Process Notifications** - Send notifications
11. **Check Audit Trail** - Verify all operations are logged
12. **Get System Metrics** - Check system performance
13. **Update Alert** - Test alert editing
14. **Deactivate Alert** - Test alert deactivation
15. **Delete Alerts** - Cleanup test data
16. **Test Scheduled Jobs** - Verify job scheduling

### 2. Quick Test (`quick_alert_test.sh`)
**Purpose**: Fast validation of core alert functionality
**Runtime**: ~30 seconds
**Coverage**: Essential create → collect → process → check flow

#### Usage:
```bash
./quick_alert_test.sh
```

#### Test Flow:
1. API Health Check
2. Create Analyst Grade Alert
3. Create Earnings Alert
4. List Alerts
5. Collect Analyst Grades Data
6. Collect Earnings Data
7. Process Events
8. Check Alert Status
9. Check Notifications
10. Process Notifications
11. Check Audit Trail
12. Cleanup Test Alerts

## Manual Testing with Individual curl Commands

### Create Analyst Grade Change Alert

```bash
curl -X POST \
  -H "Content-Type: application/json" \
  -d '{
    "alert_name": "Test Analyst Grade Alert",
    "alert_type": "grade_change",
    "alert_category": "custom",
    "entity_filters": {
      "symbols": ["AAPL", "MSFT", "GOOGL"]
    },
    "event_filters": {
      "min_confidence": 0.7,
      "min_priority": 2,
      "data_sources": ["fmp"],
      "include_upgrades": true,
      "include_downgrades": true,
      "tier_1_firms_only": false
    },
    "trigger_conditions": {
      "cooldown_minutes": 60,
      "max_alerts_per_day": 10
    },
    "suppression_rules": {
      "suppress_duplicates": true,
      "suppress_weekends": false
    },
    "notification_config": {
      "channels": ["email"]
    },
    "priority_level": 3,
    "is_test": true
  }' \
  "http://localhost:8001/api/v1/universal-alerts/alerts?user_id=4f8b2cb1-4ed6-4fb5-bd44-48e5acc830a4"
```

### Create Earnings Calendar Alert

```bash
curl -X POST \
  -H "Content-Type: application/json" \
  -d '{
    "alert_name": "Test Earnings Calendar Alert",
    "alert_type": "earnings",
    "alert_category": "custom",
    "entity_filters": {
      "symbols": ["AAPL", "MSFT", "GOOGL", "TSLA"]
    },
    "event_filters": {
      "min_confidence": 0.8,
      "min_priority": 1,
      "data_sources": ["fmp"],
      "min_days_ahead": 7,
      "max_days_ahead": 1,
      "include_surprises": true
    },
    "trigger_conditions": {
      "cooldown_minutes": 120,
      "max_alerts_per_day": 5
    },
    "suppression_rules": {
      "suppress_duplicates": true,
      "suppress_weekends": true
    },
    "notification_config": {
      "channels": ["email"]
    },
    "priority_level": 2,
    "is_test": true
  }' \
  "http://localhost:8001/api/v1/universal-alerts/alerts?user_id=4f8b2cb1-4ed6-4fb5-bd44-48e5acc830a4"
```

### Collect Analyst Grades Data

```bash
curl -X POST \
  -H "Content-Type: application/json" \
  -d '{
    "analyst_grades": {
      "sources": ["fmp"],
      "fmp_api_key": "demo",
      "symbols": ["AAPL", "MSFT", "GOOGL"]
    }
  }' \
  "http://localhost:8001/api/v1/universal-alerts/data-collection/collect"
```

### Collect Earnings Calendar Data

```bash
curl -X POST \
  -H "Content-Type: application/json" \
  -d '{
    "earnings_calendar": {
      "sources": ["fmp"],
      "fmp_api_key": "demo"
    }
  }' \
  "http://localhost:8001/api/v1/universal-alerts/data-collection/collect"
```

### Process Events (Trigger Alert Evaluation)

```bash
curl -X POST \
  "http://localhost:8001/api/v1/universal-alerts/events/process"
```

### Process Notifications (Send Emails)

```bash
curl -X POST \
  "http://localhost:8001/api/v1/universal-alerts/notifications/process"
```

### Check Alert Status

```bash
# Replace ALERT_ID with actual alert ID from creation response
curl -X GET \
  "http://localhost:8001/api/v1/universal-alerts/alerts/ALERT_ID?user_id=4f8b2cb1-4ed6-4fb5-bd44-48e5acc830a4"
```

### List User Alerts

```bash
curl -X GET \
  "http://localhost:8001/api/v1/universal-alerts/alerts?user_id=4f8b2cb1-4ed6-4fb5-bd44-48e5acc830a4"
```

### Check Notification Queue

```bash
curl -X GET \
  "http://localhost:8001/api/v1/universal-alerts/notifications/queue"
```

### Check Audit Trail

```bash
curl -X GET \
  "http://localhost:8001/api/v1/universal-alerts/audit-trail?limit=10"
```

### Get System Metrics

```bash
curl -X GET \
  "http://localhost:8001/api/v1/universal-alerts/metrics"
```

### Update Alert

```bash
curl -X PUT \
  -H "Content-Type: application/json" \
  -d '{
    "alert_name": "Updated Alert Name",
    "priority_level": 4,
    "is_active": false
  }' \
  "http://localhost:8001/api/v1/universal-alerts/alerts/ALERT_ID?user_id=4f8b2cb1-4ed6-4fb5-bd44-48e5acc830a4"
```

### Delete Alert

```bash
curl -X DELETE \
  "http://localhost:8001/api/v1/universal-alerts/alerts/ALERT_ID?user_id=4f8b2cb1-4ed6-4fb5-bd44-48e5acc830a4"
```

## Expected Test Results

### Successful Alert Creation Response
```json
{
  "success": true,
  "alert_id": "123e4567-e89b-12d3-a456-426614174000",
  "message": "Alert created successfully"
}
```

### Successful Data Collection Response
```json
{
  "success": true,
  "total_events_collected": 15,
  "results": {
    "analyst_grades": [
      {
        "event_id": "event-123",
        "symbol": "AAPL",
        "event_type": "grade_change"
      }
    ]
  }
}
```

### Successful Event Processing Response
```json
{
  "success": true,
  "events_processed": 15,
  "alerts_triggered": 3,
  "notifications_queued": 3
}
```

## Troubleshooting

### Common Issues

1. **API Not Accessible**
   - Ensure Python worker is running on port 8001
   - Check firewall settings
   - Verify database connection

2. **Alert Creation Fails**
   - Check user ID is valid
   - Verify required fields are present
   - Ensure alert type is supported

3. **Data Collection Fails**
   - Verify API keys (use "demo" for testing)
   - Check data source availability
   - Ensure symbols are valid

4. **No Events Processed**
   - Check if events were collected
   - Verify alert conditions match events
   - Check alert is active

5. **Notifications Not Sent**
   - Verify email configuration
   - Check notification queue status
   - Ensure SMTP settings are correct

### Debug Commands

```bash
# Check API health
curl -s "http://localhost:8001/api/v1/universal-alerts/health" | jq

# Check database connection
curl -s "http://localhost:8001/api/v1/universal-alerts/health" | jq '.checks.database'

# Check recent errors
curl -s "http://localhost:8001/api/v1/universal-alerts/audit-trail?status=failed&limit=5" | jq

# Check plugin status
curl -s "http://localhost:8001/api/v1/universal-alerts/plugins" | jq
```

## Performance Testing

### Load Test Script
```bash
#!/bin/bash
# Create 100 alerts rapidly
for i in {1..100}; do
  curl -s -X POST \
    -H "Content-Type: application/json" \
    -d "{\"alert_name\":\"Load Test Alert $i\",\"alert_type\":\"grade_change\",\"entity_filters\":{\"symbols\":[\"AAPL\"]},\"notification_config\":{\"channels\":[\"email\"]},\"priority_level\":3,\"is_test\":true}" \
    "http://localhost:8001/api/v1/universal-alerts/alerts?user_id=4f8b2cb1-4ed6-4fb5-bd44-48e5acc830a4" &
done
wait
echo "Load test complete"
```

## Integration with CI/CD

### GitHub Actions Example
```yaml
name: Alert API Tests
on: [push, pull_request]
jobs:
  test-api:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      - name: Start API Server
        run: |
          cd python-worker
          python start_api_server.py &
          sleep 10
      - name: Run API Tests
        run: ./test_alert_api_flow.sh
```

## Test Data Cleanup

### Cleanup Script
```bash
#!/bin/bash
# Clean up all test alerts
USER_ID="4f8b2cb1-4ed6-4fb5-bd44-48e5acc830a4"

# Get all test alerts
TEST_ALERTS=$(curl -s "http://localhost:8001/api/v1/universal-alerts/alerts?user_id=$USER_ID" | jq -r '.alerts[] | select(.is_test == true) | .alert_id')

# Delete each test alert
for alert_id in $TEST_ALERTS; do
  curl -s -X DELETE "http://localhost:8001/api/v1/universal-alerts/alerts/$alert_id?user_id=$USER_ID"
done

echo "Test alerts cleaned up"
```

## Next Steps

1. **Run Quick Test First**: Validate basic functionality
2. **Run Comprehensive Test**: Test all features
3. **Check Results**: Verify all tests pass
4. **Review Logs**: Check application logs for any issues
5. **Test UI**: Verify Streamlit UI works with API
6. **Performance Test**: Test under load
7. **Integration Test**: Test with real data sources

This comprehensive test suite ensures your Universal Alert System API is working correctly from alert creation through notification delivery.
