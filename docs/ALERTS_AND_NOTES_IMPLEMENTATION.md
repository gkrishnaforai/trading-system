# Alerts and Notes Implementation

## Overview

This document describes the implementation of notes and pluggable alerts system for the Trading System. The system follows industry standards for extensible, pluggable alert architectures.

## Features Implemented

### 1. Notes System

- **Portfolio-level notes**: Users can add notes to portfolios
- **Stock-level notes**: Users can add notes to individual holdings/stocks
- **CRUD operations**: Full Create, Read, Update, Delete support

### 2. Pluggable Alert System

- **Extensible architecture**: New alert types can be added without code changes
- **Database-driven**: Alert types can be configured via database
- **Plugin-based**: Uses plugin pattern for alert handlers
- **Multiple channels**: Supports Email, SMS, Push, Webhook notifications
- **Alert types**: Price threshold, Signal change, Volume spike, RSI extreme, MACD crossover, Portfolio risk

## Architecture

### Database Schema

#### Migration: `004_add_notes_and_alerts.sql`

**Tables Added:**

1. **alert_types**: Defines available alert types (pluggable)
2. **alerts**: User-configured alerts (portfolio or stock level)
3. **alert_notifications**: History of triggered alerts
4. **notification_channels**: User notification preferences (email, SMS, etc.)

**Fields Added:**

- `portfolios.notes`: TEXT field for portfolio notes
- `holdings.notes`: TEXT field for stock/holding notes

### Alert Plugin System

#### Base Classes

**`BaseAlertPlugin`** (`python-worker/app/alerts/base.py`):

- Abstract base class for all alert plugins
- Methods:
  - `get_metadata()`: Returns alert plugin metadata
  - `evaluate()`: Evaluates alert condition
  - `send_notification()`: Sends notification via channel
  - `validate_config()`: Validates alert configuration

**`AlertRegistry`** (`python-worker/app/alerts/registry.py`):

- Central registry for alert plugins
- Singleton pattern
- Supports dynamic plugin registration
- Methods:
  - `register()`: Register a plugin
  - `get()`: Get plugin by type ID
  - `list_plugins()`: List all registered plugins

**`AlertService`** (`python-worker/app/alerts/service.py`):

- Service layer for alert management
- Handles CRUD operations
- Evaluates alerts
- Sends notifications
- Methods:
  - `create_alert()`: Create new alert
  - `get_alert()`: Get alert by ID
  - `list_alerts()`: List alerts for user
  - `update_alert()`: Update alert
  - `delete_alert()`: Delete alert
  - `evaluate_alerts()`: Evaluate all alerts for context

#### Alert Plugins

**EmailAlertPlugin** (`python-worker/app/alerts/plugins/email_alert.py`):

- Sends alerts via email (SMTP)
- Supports all alert types
- Configurable SMTP settings

**SMSAlertPlugin** (`python-worker/app/alerts/plugins/sms_alert.py`):

- Sends alerts via SMS (Twilio or AWS SNS)
- Supports all alert types
- Configurable provider settings

### API Endpoints

#### Go API (Portfolio & Stock CRUD)

**Portfolio Endpoints:**

- `POST /api/v1/portfolio/:user_id` - Create portfolio (with notes)
- `GET /api/v1/portfolio/:user_id/:portfolio_id` - Get portfolio (with notes)
- `PUT /api/v1/portfolio/:user_id/:portfolio_id` - Update portfolio (notes)
- `DELETE /api/v1/portfolio/:user_id/:portfolio_id` - Delete portfolio

**Holding/Stock Endpoints:**

- `POST /api/v1/portfolio/:user_id/:portfolio_id/holdings` - Create holding (with notes)
- `PUT /api/v1/holdings/:holding_id` - Update holding (notes)
- `DELETE /api/v1/holdings/:holding_id` - Delete holding

#### Python API (Alerts)

**Alert Endpoints:**

- `POST /api/v1/alerts?user_id=:user_id` - Create alert
- `GET /api/v1/alerts/{alert_id}` - Get alert
- `GET /api/v1/alerts?user_id=:user_id` - List alerts
- `PUT /api/v1/alerts/{alert_id}` - Update alert
- `DELETE /api/v1/alerts/{alert_id}` - Delete alert
- `POST /api/v1/alerts/evaluate` - Evaluate alerts

## Adding New Alert Types (Without Code Changes)

### Method 1: Database Entry

Insert into `alert_types` table:

```sql
INSERT INTO alert_types
(alert_type_id, name, display_name, description, plugin_name, config_schema, subscription_level_required)
VALUES
('custom_alert', 'custom_alert', 'Custom Alert', 'My custom alert', 'email_alert',
 '{"type": "object", "properties": {"threshold": {"type": "number"}}}', 'basic');
```

The alert will be available immediately - no code changes needed!

### Method 2: Configuration File

Add to `plugins.yaml`:

```yaml
alerts:
  - module: app.alerts.plugins.email_alert
    class: EmailAlertPlugin
    config:
      alert_type_id: custom_alert
```

### Method 3: Custom Plugin (For Advanced Logic)

1. Create new plugin class extending `BaseAlertPlugin`
2. Implement `evaluate()` method with custom logic
3. Register plugin:
   ```python
   from app.alerts.registry import get_alert_registry
   registry = get_alert_registry()
   registry.register(MyCustomAlertPlugin, "custom_alert")
   ```

## Usage Examples

### Create Portfolio with Notes

```bash
curl -X POST http://localhost:8000/api/v1/portfolio/user1 \
  -H "Content-Type: application/json" \
  -d '{
    "portfolio_name": "My Portfolio",
    "notes": "This is my main trading portfolio"
  }'
```

### Create Stock/Holding with Notes

```bash
curl -X POST http://localhost:8000/api/v1/portfolio/user1/portfolio1/holdings \
  -H "Content-Type: application/json" \
  -d '{
    "stock_symbol": "AAPL",
    "quantity": 10,
    "avg_entry_price": 150.0,
    "position_type": "long",
    "notes": "Bought on dip, holding for long term",
    "purchase_date": "2025-01-15"
  }'
```

### Create Alert

```bash
curl -X POST "http://localhost:8001/api/v1/alerts?user_id=user1" \
  -H "Content-Type: application/json" \
  -d '{
    "alert_type_id": "price_threshold",
    "name": "AAPL Price Alert",
    "config": {
      "alert_type": "price_threshold",
      "threshold": 200.0,
      "direction": "above"
    },
    "notification_channels": ["email", "sms"],
    "stock_symbol": "AAPL",
    "enabled": true
  }'
```

### Evaluate Alerts

```bash
curl -X POST http://localhost:8001/api/v1/alerts/evaluate \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "user1",
    "stock_symbol": "AAPL",
    "current_price": 250.0,
    "indicators": {"rsi": 65.0},
    "signal": "buy"
  }'
```

## Testing

Comprehensive test suite: `python-worker/tests/test_alerts_and_notes.py`

**Test Coverage:**

- ✅ Portfolio CRUD with notes
- ✅ Stock/Holding CRUD with notes
- ✅ Alert CRUD operations
- ✅ Alert evaluation (price threshold, signal change)
- ✅ Email notification (test mode)
- ✅ SMS notification (test mode)
- ✅ Plugin registry functionality
- ✅ Database-driven alert types

**Run Tests:**

```bash
cd python-worker
python -m pytest tests/test_alerts_and_notes.py -v
```

## Design Principles

### SOLID Principles

- **Single Responsibility**: Each class has one clear purpose
- **Open/Closed**: Open for extension (new alert types), closed for modification
- **Liskov Substitution**: All alert plugins are interchangeable
- **Interface Segregation**: Clear, focused interfaces
- **Dependency Inversion**: Depend on abstractions (BaseAlertPlugin)

### DRY (Don't Repeat Yourself)

- Shared alert evaluation logic in base plugin
- Common notification sending patterns
- Reusable validation methods

### Fail-Fast

- No workarounds or fallbacks
- Clear error messages
- Exception hierarchy for different error types
- Validation at API boundaries

### Industry Standards

- **Plugin Pattern**: Standard plugin architecture
- **Registry Pattern**: Centralized plugin management
- **Service Layer**: Clear separation of concerns
- **Database-Driven Configuration**: Extensibility without code changes

## Future Enhancements

1. **Push Notifications**: Add push notification plugin
2. **Webhook Alerts**: Add webhook plugin for integrations
3. **Alert Templates**: Pre-configured alert templates
4. **Alert Scheduling**: Schedule alerts for specific times
5. **Alert Groups**: Group alerts for batch operations
6. **Alert Analytics**: Track alert performance and effectiveness

## Configuration

### Email Configuration

Set environment variables:

```bash
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=your-email@gmail.com
SMTP_PASSWORD=your-password
```

### SMS Configuration

**Twilio:**

```bash
TWILIO_ACCOUNT_SID=your-account-sid
TWILIO_AUTH_TOKEN=your-auth-token
TWILIO_FROM_NUMBER=+1234567890
```

**AWS SNS:**

```bash
AWS_ACCESS_KEY_ID=your-key
AWS_SECRET_ACCESS_KEY=your-secret
AWS_REGION=us-east-1
```

## Error Handling

All errors follow fail-fast principle:

- **ValidationError**: Invalid input data
- **AlertNotificationError**: Notification sending failed
- **DatabaseError**: Database operation failed
- **TradingSystemError**: Base exception for all system errors

No silent failures, no workarounds - errors are logged and raised immediately.
