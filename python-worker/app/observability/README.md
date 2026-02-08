# Universal Alert API Logging System

## 📊 Overview

The Universal Alert API now has comprehensive logging at multiple levels to provide complete visibility into all API operations. This includes request/response logging, operation tracking, performance metrics, and audit trails.

## 🚀 Quick Start

### 1. Start the Python Worker
```bash
cd /Users/krishnag/tools/trading-system/python-worker
python start_api_server.py
```

### 2. Make API Calls (from Streamlit or curl)
```bash
# Create an alert
curl -X POST "http://localhost:8001/api/v1/universal-alerts/alerts?user_id=4f8b2cb1-4ed6-4fb5-bd44-48e5acc830a4" \
  -H "Content-Type: application/json" \
  -d '{
    "alert_name": "Test Alert",
    "alert_type": "grade_change",
    "notification_config": {"channels": ["email"]},
    "entity_filters": {"symbols": ["AAPL"]},
    "priority_level": 3
  }'
```

### 3. View Logs
```bash
# View recent activity (last 10 minutes)
python view_logs.py

# View last hour of activity
python view_logs.py --minutes 60

# View errors only
python view_logs.py --errors

# View performance summary
python view_logs.py --performance

# View specific user activity
python view_logs.py --user 4f8b2cb1-4ed6-4fb5-bd44-48e5acc830a4

# View specific tracking ID
python view_logs.py --tracking create_alert_20240119_1234_5678
```

## 📋 Logging Levels

### **API Request/Response Logging**
- **🚀 Request Started**: Method, path, user ID, tracking ID
- **✅ Request Completed**: Status, processing time, response summary
- **❌ Request Failed**: Error details, processing time

### **Operation Logging**
- **🚀 STARTING**: Operation name, parameters, tracking ID
- **✅ COMPLETED**: Success results, tracking ID
- **❌ FAILED**: Error details, tracking ID

### **Audit Logging**
- **alert_created**: New alert creation with full details
- **alert_updated**: Alert modifications with before/after
- **alert_deleted**: Alert deletion with archived details

## 🔍 What Gets Logged

### **Create Alert API (`POST /alerts`)**
```
🚀 STARTING: create_alert
   Tracking ID: create_alert_20240119_1234_5678
   user_id: 4f8b2cb1-4ed6-4fb5-bd44-48e5acc830a4
   alert_name: Test Alert
   alert_type: grade_change
   symbols: ['AAPL']
   notification_channels: ['email']

🔧 Processing alert creation request
   tracking_id: create_alert_20240119_1234_5678
   user_id: 4f8b2cb1-4ed6-4fb5-bd44-48e5acc830a4
   alert_name: Test Alert
   alert_type: grade_change

✅ Alert configuration validated
   tracking_id: create_alert_20240119_1234_5678
   validation: passed

📝 Calling alert service to create alert
   tracking_id: create_alert_20240119_1234_5678
   service: universal_alert_service
   method: create_alert

✅ COMPLETED: create_alert
   Tracking ID: create_alert_20240119_1234_5678
   alert_id: 12345678-1234-5678-9abc-123456789012
   user_id: 4f8b2cb1-4ed6-4fb5-bd44-48e5acc830a4
   alert_name: Test Alert
```

### **Get Alerts API (`GET /alerts`)**
```
🚀 API Call Started: GET /alerts
   tracking_id: get_alerts_20240119_1234_5678
   user_id: 4f8b2cb1-4ed6-4fb5-bd44-48e5acc830a4
   page: 1
   limit: 50

📋 Calling alert service to get alerts
   tracking_id: get_alerts_20240119_1234_5678
   service: universal_alert_service
   method: get_user_alerts

✅ API Call Completed: GET /alerts
   tracking_id: get_alerts_20240119_1234_5678
   alerts_returned: 5
   total_alerts: 5
   processing_time_ms: 45.2
```

### **Update Alert API (`PUT /alerts/{id}`)**
```
🚀 STARTING: update_alert
   Tracking ID: update_alert_20240119_1234_5678
   user_id: 4f8b2cb1-4ed6-4fb5-bd44-48e5acc830a4
   alert_id: 12345678-1234-5678-9abc-123456789012
   alert_name: Updated Alert Name

🔍 Verifying alert ownership
   tracking_id: update_alert_20240119_1234_5678
   alert_id: 12345678-1234-5678-9abc-123456789012
   user_id: 4f8b2cb1-4ed6-4fb5-bd44-48e5acc830a4

✅ COMPLETED: update_alert
   Tracking ID: update_alert_20240119_1234_5678
   alert_id: 12345678-1234-5678-9abc-123456789012
   previous_name: Test Alert
   new_name: Updated Alert Name
```

### **Delete Alert API (`DELETE /alerts/{id}`)**
```
🚀 STARTING: delete_alert
   Tracking ID: delete_alert_20240119_1234_5678
   user_id: 4f8b2cb1-4ed6-4fb5-bd44-48e5acc830a4
   alert_id: 12345678-1234-5678-9abc-123456789012

🔍 Verifying alert ownership for deletion
   tracking_id: delete_alert_20240119_1234_5678
   existing_alert_name: Test Alert
   was_active: true

✅ COMPLETED: delete_alert
   Tracking ID: delete_alert_20240119_1234_5678
   deleted_alert_name: Test Alert
   was_active: true
   trigger_count: 5
```

## 🛠️ Log Viewer CLI Commands

### **Basic Usage**
```bash
# View recent activity (default 10 minutes)
python view_logs.py

# View last hour
python view_logs.py --minutes 60

# View last 24 hours
python view_logs.py --minutes 1440
```

### **Filtering Options**
```bash
# View specific user activity
python view_logs.py --user 4f8b2cb1-4ed6-4fb5-bd44-48e5acc830a4

# View errors only
python view_logs.py --errors

# View performance summary
python view_logs.py --performance

# View specific tracking ID
python view_logs.py --tracking create_alert_20240119_1234_5678

# View specific component
python view_logs.py --component universal_alert_api
```

### **Advanced Options**
```bash
# Custom log file
python view_logs.py --log-file /path/to/custom.log

# Combine filters
python view_logs.py --user 4f8b2cb1-4ed6-4fb5-bd44-48e5acc830a4 --minutes 120
```

## 📊 Performance Metrics

The logging system automatically tracks:

- **Response Times**: Processing time for each API call
- **Success Rates**: Success/failure ratios by endpoint
- **Error Tracking**: Detailed error information and stack traces
- **User Activity**: Per-user API usage patterns
- **Alert Operations**: Create/update/delete metrics

### **Performance Summary Example**
```
📈 Performance Summary (Last 60 minutes)
================================================================================
Total API Calls: 45
Successful: 42
Failed: 3
Error Rate: 6.67%

📊 Endpoint Breakdown:
  POST /alerts: 15 calls (93.3% success)
  GET /alerts: 25 calls (100.0% success)
  PUT /alerts/{alert_id}: 3 calls (66.7% success)
  DELETE /alerts/{alert_id}: 2 calls (100.0% success)
================================================================================
```

## 🔧 Troubleshooting

### **Common Issues**

1. **No logs appearing**
   ```bash
   # Check if Python Worker is running
   ps aux | grep python
   
   # Check log file location
   python view_logs.py --log-file logs/universal_alert_api.log
   ```

2. **Missing tracking IDs**
   - Ensure API middleware is properly configured
   - Check that requests are going through the FastAPI app

3. **Performance issues**
   ```bash
   # View slow requests
   python view_logs.py --performance --minutes 30
   
   # Check for errors
   python view_logs.py --errors --minutes 30
   ```

### **Debug Mode**

For development, you can enable debug logging:
```bash
# Set log level to DEBUG
export LOG_LEVEL=DEBUG
python start_api_server.py
```

## 📁 Log File Structure

```
logs/
├── universal_alert_api.log          # Main API logs
├── universal_alert_service.log      # Service layer logs
├── database.log                     # Database operation logs
└── audit.log                        # Audit trail logs
```

## 🔍 Integration with Streamlit

The Streamlit app now shows API responses directly in the UI, providing immediate feedback. The backend logs provide additional context for debugging:

1. **Streamlit UI**: Shows API request/response for user actions
2. **Backend Logs**: Show detailed processing information
3. **Audit Trail**: Records all alert operations for compliance

## 🚨 Security Considerations

- **No sensitive data** in logs (passwords, API keys masked)
- **Request body size** logged instead of content for security
- **User IDs** truncated in display for privacy
- **Audit logs** stored separately with restricted access

## 📈 Monitoring & Alerting

The logging system is designed to integrate with monitoring tools:

- **JSON structured logs** for log aggregation systems
- **Metrics** for Prometheus/Grafana dashboards
- **Error rates** for alerting systems
- **Performance metrics** for SLA monitoring

## 🎯 Best Practices

1. **Use tracking IDs** to correlate requests across services
2. **Monitor error rates** and set up alerts for thresholds
3. **Review performance metrics** regularly
4. **Archive old logs** to manage disk space
5. **Use structured queries** for log analysis

This comprehensive logging system provides complete visibility into the Universal Alert API operations, making it easy to debug issues, monitor performance, and maintain audit trails.
