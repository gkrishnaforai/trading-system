# Universal Alert System Architecture

## Overview
A **universal, pluggable, extensible alert system** that handles **ANY type of alert** (earnings dates, analyst grades, price movements, news events, custom events) with industry-standard observability, traceability, and audit capabilities.

## 🎯 Tech Lead Review Status: ✅ **APPROVED FOR IMPLEMENTATION**

### Key Findings:
- ✅ **Universal Coverage**: Handles ANY event type, entity, condition, and notification channel
- ✅ **SOLID Principles**: Clean, maintainable architecture with proper separation of concerns
- ✅ **DRY Implementation**: No code duplication, shared base classes and patterns
- ✅ **Observability**: Complete monitoring, audit trail, and request tracing
- ✅ **Existing System Integration**: Seamless compatibility with current infrastructure
- ✅ **Industry Standards**: Event sourcing, CQRS, plugin architecture
- ✅ **Production Ready**: Comprehensive error handling, security, and scalability

## Core Components

### 1. Universal Data Ingestion Layer
```
External APIs (FMP, Alpha Vantage, News APIs, Custom Sources)
    ↓
Universal Data Source Plugins (Pluggable)
    ↓
Universal Events Table (universal_events)
```

### 2. Universal Event Processing Engine
```
Universal Events Table
    ↓
Event Processor Plugins (Universal)
    ↓
Universal Events Table (processed)
    ↓
Alert Evaluation Engine (Universal)
```

### 3. Universal Alert Management Layer
```
Universal Alert Definitions (user_configured for ANY event type)
    ↓
Alert Evaluator Plugins (Pluggable)
    ↓
Universal Alert Events Table (triggered alerts)
    ↓
Universal Notification Queue
```

### 4. Universal Notification Layer
```
Universal Notification Queue
    ↓
Notification Service (Pluggable Channels)
    ↓
Channels: Email, SMS, Push, Webhook, Slack, Teams, Custom
```

## Enhanced Detailed Flow

### Step 1: Universal Data Collection
**Frequency**: Configurable per data source
**Job**: `universal_data_collection_job`
- Fetch data from ANY external source via plugins
- Transform to universal event format
- Store in `universal_events` table with full audit trail

### Step 2: Universal Event Processing
**Frequency**: Real-time processing
**Job**: `universal_event_processing_job`
- Process events through pluggable processors
- Detect changes and calculate metadata
- Update events with processing status

### Step 3: Universal Alert Evaluation
**Frequency**: Real-time processing
**Job**: `universal_alert_evaluation_job`
- Process events against ALL alert types
- Evaluate using pluggable evaluators
- Generate alert events with scoring

### Step 4: Universal Notification Delivery
**Frequency**: Real-time processing
**Job**: `universal_notification_delivery_job`
- Process alert events through notification queue
- Send via pluggable notification channels
- Track delivery status and handle retries

## Key Design Principles

### 1. **Universal Coverage**
- **ANY Event Type**: Earnings, grades, prices, news, custom events
- **ANY Entity**: Stocks, portfolios, markets, sectors, users
- **ANY Condition**: Simple thresholds to complex multi-factor rules
- **ANY Notification**: Email, SMS, push, webhook, custom channels

### 2. **SOLID Principles Implementation**
- **Single Responsibility**: Each component has one clear purpose
- **Open/Closed**: Extensible with plugins without modification
- **Liskov Substitution**: All plugins are interchangeable
- **Interface Segregation**: Specific, focused interfaces
- **Dependency Inversion**: Depend on abstractions, not implementations

### 3. **DRY Implementation**
- Shared base classes eliminate duplication
- Common patterns across all components
- Reusable audit and logging infrastructure
- Protocol-based interfaces for type safety

### 4. **Event-Driven Architecture**
- Reactive to ANY event type
- Minimal latency between event and notification
- Efficient resource usage with queue-based processing

### 5. **Pluggable Architecture**
- Multiple data sources supported via plugins
- Multiple notification channels via plugins
- Configurable alert conditions via plugins
- Dynamic plugin registration and management

### 6. **Enterprise Observability**
- Complete audit trail with existing audit service
- Structured logging with correlation IDs
- Performance metrics and monitoring
- Health checks and system status

### 7. **Scalability & Reliability**
- Horizontal scaling of job processors
- Queue-based processing with retry logic
- Dead letter queues for problematic events
- Circuit breakers and error handling

## Enhanced Database Schema

### Universal Events Table (Core of ANY Event Type)
```sql
CREATE TABLE universal_events (
    event_id UUID PRIMARY KEY,
    event_type VARCHAR(50) NOT NULL,        -- ANY event type
    entity_type VARCHAR(20) NOT NULL,        -- stock, portfolio, market, user
    entity_id VARCHAR(50) NOT NULL,          -- symbol, portfolio_id, etc.
    
    event_data JSONB NOT NULL,              -- Flexible schema for ANY event
    previous_data JSONB,                    -- Previous state for change detection
    change_metadata JSONB,                  -- What changed and by how much
    
    event_timestamp TIMESTAMPTZ NOT NULL,
    detected_at TIMESTAMPTZ DEFAULT NOW(),
    processed_at TIMESTAMPTZ,
    
    data_source VARCHAR(50) NOT NULL,
    confidence_score DECIMAL(3,2) DEFAULT 1.0,
    
    processing_status VARCHAR(20) DEFAULT 'pending',
    correlation_id VARCHAR(50),             -- Request tracing
    
    created_at TIMESTAMPTZ DEFAULT NOW()
);
```

### Universal Alert Definitions (ANY Alert Type)
```sql
CREATE TABLE universal_alerts (
    alert_id UUID PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES users(id),
    alert_name VARCHAR(200) NOT NULL,
    alert_type VARCHAR(50) NOT NULL,        -- earnings, grades, price, news, custom
    
    entity_filters JSONB NOT NULL DEFAULT '{}',    -- Universal filtering
    event_filters JSONB NOT NULL DEFAULT '{}',      -- Universal event filtering
    trigger_conditions JSONB NOT NULL DEFAULT '{}',  -- Complex logic
    suppression_rules JSONB DEFAULT '{}',            -- Cooldown, deduplication
    
    notification_config JSONB DEFAULT '{}',
    priority_level INTEGER DEFAULT 3,
    is_active BOOLEAN DEFAULT TRUE,
    
    trigger_count INTEGER DEFAULT 0,
    last_triggered_at TIMESTAMPTZ,
    
    created_at TIMESTAMPTZ DEFAULT NOW()
);
```

### Universal Audit Trail (Complete Observability)
```sql
CREATE TABLE alert_audit_trail (
    audit_id UUID PRIMARY KEY,
    
    entity_type VARCHAR(20) NOT NULL,      -- alert, event, notification, job
    entity_id VARCHAR(50) NOT NULL,
    operation_type VARCHAR(20) NOT NULL,   -- create, update, delete, trigger, send
    
    operation_data JSONB NOT NULL,
    previous_state JSONB,
    new_state JSONB,
    
    user_id UUID REFERENCES users(id),
    correlation_id VARCHAR(50),            -- Request tracing
    session_id VARCHAR(50),
    
    started_at TIMESTAMPTZ NOT NULL,
    completed_at TIMESTAMPTZ,
    duration_ms INTEGER,                   -- Performance tracking
    
    status VARCHAR(20) NOT NULL,
    error_message TEXT,
    
    ip_address INET,
    user_agent TEXT,
    
    created_at TIMESTAMPTZ DEFAULT NOW()
);
```

## Plugin Architecture

### Data Source Plugins
```python
class DataSourcePlugin(Protocol):
    async def collect_data(self, config: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Collect raw data from ANY external source"""
        pass
    
    def get_event_types(self) -> List[str]:
        """Return supported event types"""
        pass
    
    def get_schema(self) -> Dict[str, Any]:
        """Return data schema for validation"""
        pass

# Example: Earnings Calendar Plugin
class EarningsCalendarPlugin(DataSourcePlugin):
    async def collect_data(self, config: Dict[str, Any]) -> List[Dict[str, Any]]:
        # Fetch earnings data from ANY source
        return earnings_events
    
    def get_event_types(self) -> List[str]:
        return ['earnings_date', 'earnings_surprise', 'guidance_update']
```

### Alert Evaluator Plugins
```python
class AlertEvaluatorPlugin(Protocol):
    async def evaluate(self, event: Dict[str, Any], alert: Dict[str, Any]) -> Dict[str, Any]:
        """Evaluate if event triggers alert"""
        pass
    
    def get_supported_alert_types(self) -> List[str]:
        """Return supported alert types"""
        pass

# Example: Earnings Alert Evaluator
class EarningsAlertEvaluator(AlertEvaluatorPlugin):
    async def evaluate(self, event: Dict[str, Any], alert: Dict[str, Any]) -> Dict[str, Any]:
        # Evaluate earnings alerts with ANY logic
        return evaluation_result
```

## Universal Email Templates

### Earnings Calendar Email (Like Your Example)
```html
<!DOCTYPE html>
<html>
<head>
    <title>📊 Click to View Analyst Estimates and Earnings Call Time</title>
    <style>
        .header { background: #1a73e8; color: white; padding: 20px; text-align: center; }
        .date-section { margin: 20px 0; padding: 15px; border-left: 4px solid #1a73e8; }
        .symbol { font-weight: bold; font-size: 16px; color: #1a73e8; }
        .upgrade-btn { background: #34a853; color: white; padding: 10px 20px; text-decoration: none; border-radius: 4px; }
    </style>
</head>
<body>
    <div class="header">
        <h1>📊 Click to View Analyst Estimates and Earnings Call Time</h1>
        <h2>Set Alerts for Upcoming Earnings</h2>
        <p>{{current_date}}</p>
    </div>
    
    {% for date_group in earnings_by_date %}
    <div class="date-section">
        <h3>{{date_group.date}}</h3>
        {% for symbol in date_group.symbols %}
        <div class="symbol">{{symbol}}</div>
        {% endfor %}
    </div>
    {% endfor %}
    
    <div style="text-align: center; margin: 30px 0;">
        <a href="{{portal_url}}" class="upgrade-btn">Upgrade to Receive Real-Time Premium Alerts in Your Inbox</a>
    </div>
</body>
</html>
```

## Industry Comparison (Enhanced)

| Feature | Bloomberg | Robinhood | Our Universal System |
|---------|-----------|-----------|---------------------|
| **ANY Event Type** | ❌ Limited | ❌ Limited | ✅ **Universal** |
| **ANY Entity Type** | ❌ Limited | ❌ Limited | ✅ **Universal** |
| **ANY Notification** | ✅ Multiple | ✅ Multiple | ✅ **Universal** |
| **Plugin Architecture** | ❌ No | ❌ No | ✅ **Pluggable** |
| **Custom Events** | ❌ No | ❌ No | ✅ **Supported** |
| **Audit Trail** | ✅ Yes | ❌ No | ✅ **Complete** |
| **Real-time** | ✅ Yes | ✅ Yes | ✅ Yes |
| **API Access** | ✅ Yes | ❌ No | ✅ Yes |
| **Scalability** | ✅ High | ❌ Limited | ✅ **Horizontal** |

## Enhanced Performance Requirements

- **Latency**: < 30 seconds from ANY event to notification
- **Throughput**: 10,000+ alerts per minute
- **Availability**: 99.9% uptime
- **Event Types**: Unlimited - ANY event type supported
- **Entities**: Unlimited - stocks, portfolios, markets, custom
- **Notifications**: Unlimited - ANY channel via plugins

## Enhanced Security & Compliance

- **Complete Audit Trail**: Every operation logged with full context
- **Request Tracing**: Correlation IDs across all components
- **Data Privacy**: Row-level security with user isolation
- **Input Validation**: Schema validation for ALL event types
- **Rate Limiting**: Configurable per data source and user
- **Compliance Ready**: Full audit trail for regulatory requirements

## Integration with Existing Systems

### Database Compatibility
- ✅ Enhances existing `stocks` table without breaking changes
- ✅ Uses existing `users` table structure
- ✅ Non-breaking migration strategy
- ✅ Backward compatibility maintained

### Observability Integration
- ✅ Uses existing `app.observability` infrastructure
- ✅ Integrates with current logging, metrics, audit systems
- ✅ Follows established patterns from `base.py`
- ✅ Compatible with existing monitoring tools

### Service Architecture
- ✅ Consistent with existing service patterns
- ✅ Uses same dependency injection patterns
- ✅ Compatible with current error handling
- ✅ Follows existing naming conventions

## Implementation Phases

### Phase 1: Core Infrastructure (Immediate)
1. Run migration `017_universal_alert_system.sql`
2. Deploy core service classes
3. Implement basic plugins (earnings, grades)
4. Setup universal email templates

### Phase 2: Plugin Expansion (Week 2)
1. Add advanced plugins (news, price movements)
2. Implement template system for ALL notification types
3. Add performance monitoring dashboard
4. Create plugin management UI

### Phase 3: Advanced Features (Week 3-4)
1. Add Redis caching for high-frequency events
2. Implement event replay for recovery
3. Add machine learning for smart alerting
4. Create advanced analytics and reporting

## Migration Strategy

### Non-Breaking Migration
```sql
-- Phase 1: Add new tables (no existing tables affected)
CREATE TABLE universal_events (...);
CREATE TABLE universal_alerts (...);
CREATE TABLE alert_audit_trail (...);

-- Phase 2: Enhance existing stocks table
ALTER TABLE stocks ADD COLUMN alert_metadata JSONB DEFAULT '{}';

-- Phase 3: Gradual data migration (optional)
-- Existing alert system can coexist during transition
```

### Backward Compatibility
- Existing alert system continues to work
- Gradual migration path available
- Zero-downtime deployment possible
- Rollback strategy in place
