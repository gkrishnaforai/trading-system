# Universal Alert System - Implementation Guide

## 🎯 Implementation Status: ✅ **COMPLETE**

The Universal Alert System has been fully implemented with all components working together. This guide provides step-by-step instructions for deployment and testing.

## 📋 Implementation Checklist

### ✅ Completed Components

1. **Database Schema** (`017_universal_alert_system.sql`)
   - Universal events table
   - Universal alerts table  
   - Alert events table
   - Notification queue table
   - Audit trail table
   - Plugin registry table

2. **Core Services**
   - `universal_alert_service_enhanced.py` - Main orchestration service
   - `universal_plugins.py` - Pluggable data source and evaluator plugins
   - `universal_scheduler.py` - Scheduled job management

3. **API Layer**
   - `universal_alert_api.py` - Complete REST API with full CRUD operations

4. **User Interface**
   - `16_Universal_Alert_System.py` - Beautiful Streamlit UI

5. **Documentation**
   - `universal_alert_system.md` - Updated architecture
   - `universal_alert_system_tech_review.md` - Tech lead review
   - Implementation guide (this document)

## 🚀 Deployment Steps

### Step 1: Database Migration
```bash
cd /Users/krishnag/tools/trading-system/python-worker

# Run the universal alert system migration
python -c "
from app.database import init_database
init_database()
print('✅ Universal Alert System database initialized')
"
```

### Step 2: Start the Python Worker
```bash
# Start the FastAPI server with universal alert system
python start_api_server.py

# The server will be available at:
# - Main API: http://127.0.0.1:8001
# - Universal Alerts API: http://127.0.0.1:8001/api/v1/universal-alerts
# - API Docs: http://127.0.0.1:8001/docs
```

### Step 3: Start Streamlit
```bash
cd /Users/krishnag/tools/trading-system/streamlit-app

# Start Streamlit with universal alert system
streamlit run pages/16_Universal_Alert_System.py

# The UI will be available at: http://localhost:8501
```

## 🧪 Testing the System

### Test 1: System Health Check
```bash
curl http://127.0.0.1:8001/api/v1/universal-alerts/health
```

Expected response:
```json
{
  "status": "healthy",
  "timestamp": "2026-01-18T20:00:00",
  "pending_events": 0,
  "plugins": {
    "data_sources": ["earnings_calendar", "analyst_grades", "price_movements"],
    "evaluators": ["earnings", "grade_change", "price_movement"],
    "notifications": ["email"]
  },
  "metrics": {...},
  "checks": {
    "database": "healthy",
    "plugins": "healthy",
    "queues": "healthy"
  }
}
```

### Test 2: Create an Earnings Alert
```bash
curl -X POST "http://127.0.0.1:8001/api/v1/universal-alerts/alerts?user_id=4f8b2cb1-4ed6-4fb5-bd44-48e5acc830a4" \
  -H "Content-Type: application/json" \
  -d '{
    "alert_name": "AAPL Earnings Alert",
    "alert_type": "earnings",
    "entity_filters": {
      "symbols": ["AAPL"]
    },
    "event_filters": {
      "min_days_ahead": 7,
      "max_days_ahead": 1,
      "include_surprises": true
    },
    "notification_config": {
      "channels": ["email"]
    },
    "priority_level": 3
  }'
```

### Test 3: Create a Grade Change Alert
```bash
curl -X POST "http://127.0.0.1:8001/api/v1/universal-alerts/alerts?user_id=4f8b2cb1-4ed6-4fb5-bd44-48e5acc830a4" \
  -H "Content-Type: application/json" \
  -d '{
    "alert_name": "Tech Stocks Grade Changes",
    "alert_type": "grade_change",
    "entity_filters": {
      "symbols": ["AAPL", "MSFT", "GOOGL"]
    },
    "event_filters": {
      "include_upgrades": true,
      "include_downgrades": true,
      "tier_1_firms_only": true
    },
    "notification_config": {
      "channels": ["email"]
    },
    "priority_level": 4
  }'
```

### Test 4: Collect Earnings Data
```bash
curl -X POST "http://127.0.0.1:8001/api/v1/universal-alerts/data-collection/collect" \
  -H "Content-Type: application/json" \
  -d '{
    "earnings_calendar": {
      "sources": ["fmp"],
      "fmp_api_key": "demo"
    }
  }'
```

### Test 5: Create a Test Event
```bash
curl -X POST "http://127.0.0.1:8001/api/v1/universal-alerts/events" \
  -H "Content-Type: application/json" \
  -d '{
    "event_type": "earnings_date",
    "entity_type": "stock",
    "entity_id": "AAPL",
    "event_data": {
      "symbol": "AAPL",
      "company_name": "Apple Inc.",
      "earnings_date": "2026-01-25",
      "eps_estimate": 2.10,
      "time": "After Market Close"
    },
    "data_source": "test",
    "confidence_score": 1.0
  }'
```

### Test 6: Get User Alerts
```bash
curl "http://127.0.0.1:8001/api/v1/universal-alerts/alerts?user_id=4f8b2cb1-4ed6-4fb5-bd44-48e5acc830a4"
```

## 🎮 Streamlit UI Testing

1. Open http://localhost:8501
2. Navigate to "16_Universal_Alert_System"
3. Test each section:

### Dashboard Page
- View system health metrics
- Check recent activity
- Use quick action buttons

### Create Alert Page
- Create different alert types (earnings, grade changes, price movements)
- Test entity and event filters
- Configure notification channels

### My Alerts Page
- View created alerts
- Test filtering and sorting
- Use alert management buttons

### System Health Page
- Monitor system status
- Check plugin health
- View system metrics

### Data Collection Page
- Test manual data collection
- Configure plugins
- Monitor collection status

### Analytics Page
- View alert statistics
- Check performance metrics
- Analyze trends

## 🔧 Configuration

### Environment Variables
Add to your `.env` file:
```bash
# Universal Alert System
UNIVERSAL_ALERTS_ENABLED=true
UNIVERSAL_SCHEDULER_ENABLED=true

# API Keys for plugins
FMP_API_KEY=your_fmp_api_key
ALPHA_VANTAGE_API_KEY=your_alpha_vantage_api_key
NEWS_API_KEY=your_news_api_key

# Email Configuration
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=your_email@gmail.com
SMTP_PASSWORD=your_app_password

# Scheduler Configuration
SCHEDULER_TIMEZONE=America/New_York
```

### Plugin Configuration
The system comes with built-in plugins:

1. **Data Source Plugins**
   - `earnings_calendar` - Collects earnings dates
   - `analyst_grades` - Collects analyst grade changes
   - `price_movements` - Collects price movements

2. **Evaluator Plugins**
   - `earnings` - Evaluates earnings alerts
   - `grade_change` - Evaluates grade change alerts
   - `price_movement` - Evaluates price movement alerts

3. **Notification Plugins**
   - `email` - Sends email notifications

## 📊 Monitoring & Observability

### Health Endpoints
- `/api/v1/universal-alerts/health` - System health
- `/api/v1/universal-alerts/metrics` - System metrics

### Audit Trail
All operations are logged to `alert_audit_trail` table with:
- Full operation context
- Before/after states
- Performance metrics
- Error details

### Metrics Collection
The system integrates with existing observability:
- Event processing metrics
- Alert trigger metrics
- Plugin performance metrics
- System health metrics

## 🎯 Example Use Cases

### 1. Earnings Calendar Email
Create an earnings alert to generate beautiful emails like your example:

```python
# Create earnings alert for multiple symbols
alert_request = {
    "alert_name": "Weekly Earnings Calendar",
    "alert_type": "earnings",
    "entity_filters": {
        "symbols": ["BKR", "NFLX", "IBKR", "MMM", "UAL"]  # Your example symbols
    },
    "event_filters": {
        "min_days_ahead": 7,
        "max_days_ahead": 0,
        "include_surprises": true
    },
    "notification_config": {
        "channels": ["email"],
        "template": "earnings_calendar"
    }
}
```

### 2. Analyst Grade Change Alerts
```python
# Create grade change alert for tier-1 firms
alert_request = {
    "alert_name": "Tier-1 Grade Changes",
    "alert_type": "grade_change",
    "entity_filters": {
        "symbols": ["AAPL", "MSFT", "GOOGL", "AMZN"]
    },
    "event_filters": {
        "include_upgrades": true,
        "include_downgrades": true,
        "tier_1_firms_only": true
    }
}
```

### 3. Price Movement Alerts
```python
# Create price movement alert
alert_request = {
    "alert_name": "Significant Price Movements",
    "alert_type": "price_movement",
    "entity_filters": {
        "symbols": ["AAPL", "MSFT", "GOOGL"]
    },
    "event_filters": {
        "min_change_percent": 5.0,
        "include_volume_spikes": true
    }
}
```

## 🔄 Scheduled Jobs

The system includes automated jobs:

1. **Earnings Data Collection** - Every 60 minutes
2. **Analyst Grades Collection** - Every 15 minutes
3. **Price Movements Collection** - Every 5 minutes
4. **Event Processing** - Every 2 minutes
5. **Notification Delivery** - Every 1 minute
6. **System Health Check** - Every 10 minutes

## 🚨 Troubleshooting

### Common Issues

1. **Database Connection Error**
   - Ensure PostgreSQL is running
   - Check DATABASE_URL in .env file
   - Verify migration was successful

2. **Plugin Errors**
   - Check API keys are configured
   - Verify external API availability
   - Check plugin logs

3. **No Events Processed**
   - Check if jobs are running
   - Verify data collection is working
   - Check event processing logs

4. **No Notifications Sent**
   - Verify notification configuration
   - Check email settings
   - Review notification queue

### Debug Commands

```bash
# Check database tables
psql $DATABASE_URL -c "\dt universal_*"

# Check pending events
curl "http://127.0.0.1:8001/api/v1/universal-alerts/events/pending"

# Check system metrics
curl "http://127.0.0.1:8001/api/v1/universal-alerts/metrics"

# View logs
docker-compose logs python-worker | grep universal_alert
```

## 🎉 Success Criteria

The system is successfully implemented when:

✅ **Database Schema**: All tables created successfully
✅ **API Endpoints**: All endpoints responding correctly
✅ **Plugin System**: Data collection and evaluation working
✅ **Streamlit UI**: Beautiful interface functional
✅ **Alert Creation**: Users can create alerts
✅ **Event Processing**: Events trigger alerts correctly
✅ **Notifications**: Alerts generate notifications
✅ **Audit Trail**: All operations logged
✅ **Monitoring**: Health checks and metrics working
✅ **Scheduled Jobs**: Automated collection running

## 📈 Next Steps

1. **Add More Plugins**
   - News events plugin
   - SEC filings plugin
   - Social sentiment plugin

2. **Enhanced Notifications**
   - SMS notifications
   - Push notifications
   - Slack/Teams integration

3. **Advanced Analytics**
   - Machine learning for smart alerts
   - Predictive analytics
   - Alert performance optimization

4. **Performance Optimization**
   - Redis caching
   - Event replay system
   - Horizontal scaling

## 🎯 Conclusion

The Universal Alert System is now **fully implemented and ready for production use**. It provides:

- **Universal Coverage**: Handles ANY event type
- **Industry Standards**: Event sourcing, CQRS, plugin architecture
- **SOLID Principles**: Clean, maintainable code
- **Full Observability**: Complete audit trail and monitoring
- **Beautiful UI**: Modern, responsive interface
- **Scalability**: Designed for enterprise use

The system can immediately handle the earnings calendar emails you showed, analyst grade changes, price movements, and any future alert type - all with the same pluggable, auditable, observable infrastructure.
