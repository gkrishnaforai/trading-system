# Universal Alert System Architecture

## Overview
A **universal, pluggable, extensible alert system** that handles ANY type of alert (earnings dates, analyst grades, price movements, news events, etc.) with industry-standard observability, traceability, and audit capabilities.

## Core Design Principles

### 🏗️ **SOLID Principles**
- **S**ingle Responsibility: Each component has one clear purpose
- **O**pen/Closed: Extensible without modification
- **L**iskov Substitution: Pluggable components are interchangeable
- **I**nterface Segregation: Specific interfaces for each concern
- **D**ependency Inversion: Depend on abstractions, not implementations

### 🔧 **DRY (Don't Repeat Yourself)**
- Shared base classes and utilities
- Common patterns for all alert types
- Reusable components across domains

### 📊 **Industry Standards**
- Event Sourcing for audit trails
- Command Query Responsibility Segregation (CQRS)
- Observer Pattern for event handling
- Strategy Pattern for pluggable algorithms
- Factory Pattern for component creation

## Enhanced Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    Universal Alert System                        │
├─────────────────────────────────────────────────────────────────┤
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────┐ │
│  │   Data      │  │   Event     │  │   Alert     │  │  Audit  │ │
│  │ Ingestion   │→│  Processing │→│ Evaluation  │→│ Service │ │
│  │  (Pluggable)│  │ (Universal) │  │ (Pluggable)│  │(Unified)│ │
│  └─────────────┘  └─────────────┘  └─────────────┘  └─────────┘ │
│         ↓               ↓               ↓               ↓        │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────┐ │
│  │   Raw       │  │   Events    │  │   Alerts    │  │  Audit  │ │
│  │   Data      │  │   Queue     │  │   Queue     │  │  Trail │ │
│  │  Tables     │  │  (Unified)  │  │ (Unified)   │  │(Events) │ │
│  └─────────────┘  └─────────────┘  └─────────────┘  └─────────┘ │
│         ↓               ↓               ↓               ↓        │
│  ┌─────────────────────────────────────────────────────────────┐ │
│  │               Notification Service (Pluggable)               │ │
│  │  ┌─────────┐  ┌─────────┐  ┌─────────┐  ┌─────────────────┐  │ │
│  │  │  Email  │  │   SMS   │  │  Push   │  │   Webhook      │  │ │
│  │  │Channel  │  │Channel  │  │Channel  │  │   Channel       │  │ │
│  │  └─────────┘  └─────────┘  └─────────┘  └─────────────────┘  │ │
│  └─────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────┘
```

## Universal Data Model

### 1. **Enhanced Stocks Table**
```sql
-- Add alert-specific columns to existing stocks table
ALTER TABLE stocks ADD COLUMN alert_metadata JSONB DEFAULT '{}';
ALTER TABLE stocks ADD COLUMN last_alert_check TIMESTAMP;
ALTER TABLE stocks ADD COLUMN alert_subscription_count INTEGER DEFAULT 0;
ALTER TABLE stocks ADD COLUMN alert_events_count INTEGER DEFAULT 0;

-- Indexes for alert performance
CREATE INDEX idx_stocks_alert_check ON stocks(last_alert_check) WHERE last_alert_check IS NOT NULL;
CREATE INDEX idx_stocks_alert_metadata ON stocks USING GIN(alert_metadata);
```

### 2. **Universal Event System**
```sql
-- Universal events table for ALL alert types
CREATE TABLE IF NOT EXISTS universal_events (
    event_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    event_type VARCHAR(50) NOT NULL, -- 'earnings_date', 'grade_change', 'price_alert', 'news_event'
    entity_type VARCHAR(20) NOT NULL, -- 'stock', 'portfolio', 'market'
    entity_id VARCHAR(50) NOT NULL, -- stock symbol, portfolio ID, etc.
    
    -- Event data (flexible schema)
    event_data JSONB NOT NULL, -- Specific to event type
    previous_data JSONB, -- Previous state for change detection
    change_metadata JSONB, -- What changed and by how much
    
    -- Temporal data
    event_timestamp TIMESTAMPTZ NOT NULL,
    detected_at TIMESTAMPTZ DEFAULT NOW(),
    processed_at TIMESTAMPTZ,
    
    -- Source and provenance
    data_source VARCHAR(50) NOT NULL,
    source_id VARCHAR(100),
    confidence_score DECIMAL(3,2) DEFAULT 1.0,
    
    -- Processing metadata
    processing_status VARCHAR(20) DEFAULT 'pending',
    error_message TEXT,
    retry_count INTEGER DEFAULT 0,
    
    -- Audit fields
    correlation_id VARCHAR(50),
    parent_event_id UUID REFERENCES universal_events(event_id),
    
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    
    -- Constraints
    CHECK (processing_status IN ('pending', 'processing', 'completed', 'failed', 'cancelled')),
    CHECK (confidence_score BETWEEN 0.0 AND 1.0)
);

-- Universal alert definitions table
CREATE TABLE IF NOT EXISTS universal_alerts (
    alert_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    alert_name VARCHAR(200) NOT NULL,
    alert_type VARCHAR(50) NOT NULL, -- 'earnings', 'grades', 'price', 'news', 'custom'
    
    -- Target criteria (universal)
    entity_filters JSONB NOT NULL DEFAULT '{}', -- {"symbols": ["AAPL"], "sectors": ["Tech"]}
    event_filters JSONB NOT NULL DEFAULT '{}', -- {"change_types": ["upgrade"], "min_change": 0.3}
    
    -- Advanced conditions
    trigger_conditions JSONB NOT NULL DEFAULT '{}', -- Complex logic, time windows, etc.
    suppression_rules JSONB DEFAULT '{}', -- Cooldown, deduplication, etc.
    
    -- Configuration
    notification_config JSONB DEFAULT '{}',
    priority_level INTEGER DEFAULT 3 CHECK (priority_level BETWEEN 1 AND 5),
    is_active BOOLEAN DEFAULT TRUE,
    
    -- Statistics
    trigger_count INTEGER DEFAULT 0,
    last_triggered_at TIMESTAMPTZ,
    success_count INTEGER DEFAULT 0,
    failure_count INTEGER DEFAULT 0,
    
    -- Audit fields
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Universal alert events (triggered alerts)
CREATE TABLE IF NOT EXISTS universal_alert_events (
    event_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    alert_id UUID NOT NULL REFERENCES universal_alerts(alert_id) ON DELETE CASCADE,
    universal_event_id UUID NOT NULL REFERENCES universal_events(event_id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    
    -- Evaluation metadata
    match_score DECIMAL(5,2),
    trigger_reason TEXT NOT NULL,
    urgency_level VARCHAR(20) DEFAULT 'medium',
    
    -- Processing status
    status VARCHAR(20) DEFAULT 'pending',
    processed_at TIMESTAMPTZ,
    sent_at TIMESTAMPTZ,
    error_message TEXT,
    
    -- Audit fields
    correlation_id VARCHAR(50),
    created_at TIMESTAMPTZ DEFAULT NOW()
);
```

### 3. **Unified Audit Service Integration**
```sql
-- Extend existing audit service for alerts
CREATE TABLE IF NOT EXISTS alert_audit_trail (
    audit_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    
    -- Entity information
    entity_type VARCHAR(20) NOT NULL, -- 'alert', 'event', 'notification', 'job'
    entity_id VARCHAR(50) NOT NULL,
    operation_type VARCHAR(20) NOT NULL, -- 'create', 'update', 'delete', 'trigger', 'send'
    
    -- Operation details
    operation_data JSONB NOT NULL,
    previous_state JSONB,
    new_state JSONB,
    
    -- Execution context
    user_id UUID REFERENCES users(id),
    job_id VARCHAR(50),
    correlation_id VARCHAR(50),
    
    -- Results
    status VARCHAR(20) NOT NULL,
    result_data JSONB,
    error_message TEXT,
    error_stack TEXT,
    
    -- Timing
    started_at TIMESTAMPTZ NOT NULL,
    completed_at TIMESTAMPTZ,
    duration_ms INTEGER,
    
    -- Metadata
    ip_address INET,
    user_agent TEXT,
    session_id VARCHAR(50),
    
    created_at TIMESTAMPTZ DEFAULT NOW()
);
```

## Pluggable Component System

### 1. **Data Source Plugins**
```python
# Abstract base for all data sources
class DataSourcePlugin(ABC):
    @abstractmethod
    async def collect_data(self, config: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Collect raw data from external source"""
        pass
    
    @abstractmethod
    def get_event_types(self) -> List[str]:
        """Return supported event types"""
        pass
    
    @abstractmethod
    def get_schema(self) -> Dict[str, Any]:
        """Return data schema for validation"""
        pass

# Example: Earnings Calendar Plugin
class EarningsCalendarPlugin(DataSourcePlugin):
    async def collect_data(self, config: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Collect earnings calendar data"""
        # Fetch from external APIs
        # Transform to universal event format
        pass
    
    def get_event_types(self) -> List[str]:
        return ['earnings_date', 'earnings_surprise', 'guidance_update']

# Example: Analyst Grades Plugin
class AnalystGradesPlugin(DataSourcePlugin):
    async def collect_data(self, config: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Collect analyst grade changes"""
        pass
    
    def get_event_types(self) -> List[str]:
        return ['grade_change', 'consensus_update', 'price_target_change']
```

### 2. **Event Processor Plugins**
```python
class EventProcessorPlugin(ABC):
    @abstractmethod
    async def process_event(self, event: Dict[str, Any]) -> ProcessedEvent:
        """Process raw event into standardized format"""
        pass
    
    @abstractmethod
    def get_supported_types(self) -> List[str]:
        """Return supported event types"""
        pass

class EarningsEventProcessor(EventProcessorPlugin):
    async def process_event(self, event: Dict[str, Any]) -> ProcessedEvent:
        """Process earnings-related events"""
        # Standardize earnings data
        # Calculate surprises, changes, etc.
        pass
```

### 3. **Alert Evaluator Plugins**
```python
class AlertEvaluatorPlugin(ABC):
    @abstractmethod
    async def evaluate(self, event: Dict[str, Any], alert: Dict[str, Any]) -> EvaluationResult:
        """Evaluate if event triggers alert"""
        pass
    
    @abstractmethod
    def get_supported_alert_types(self) -> List[str]:
        """Return supported alert types"""
        pass

class EarningsAlertEvaluator(AlertEvaluatorPlugin):
    async def evaluate(self, event: Dict[str, Any], alert: Dict[str, Any]) -> EvaluationResult:
        """Evaluate earnings alerts"""
        # Check earnings date proximity, surprise magnitude, etc.
        pass
```

## Universal Email Templates

### 1. **Earnings Calendar Email** (Like your example)
```html
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>Upcoming Earnings Alerts</title>
    <style>
        .header { background: #1a73e8; color: white; padding: 20px; text-align: center; }
        .date-section { margin: 20px 0; padding: 15px; border-left: 4px solid #1a73e8; }
        .symbol { font-weight: bold; font-size: 16px; color: #1a73e8; }
        .footer { text-align: center; padding: 20px; color: #666; font-size: 12px; }
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
    
    <div class="footer">
        <p>This alert was generated by Universal Alert System</p>
        <p><a href="{{unsubscribe_url}}">Unsubscribe</a> | <a href="{{preferences_url}}">Manage Preferences</a></p>
    </div>
</body>
</html>
```

## Observability & Monitoring

### 1. **Metrics Collection**
```python
class AlertMetrics:
    """Universal alert metrics collection"""
    
    def __init__(self):
        self.counters = {
            'events_processed': Counter('alert_events_processed_total', ['event_type']),
            'alerts_triggered': Counter('alert_alerts_triggered_total', ['alert_type', 'urgency']),
            'notifications_sent': Counter('alert_notifications_sent_total', ['channel']),
            'processing_duration': Histogram('alert_processing_duration_seconds', ['event_type']),
            'queue_size': Gauge('alert_queue_size', ['queue_type'])
        }
    
    def record_event_processed(self, event_type: str, duration: float):
        self.counters['events_processed'].labels(event_type=event_type).inc()
        self.counters['processing_duration'].labels(event_type=event_type).observe(duration)
    
    def record_alert_triggered(self, alert_type: str, urgency: str):
        self.counters['alerts_triggered'].labels(alert_type=alert_type, urgency=urgency).inc()
```

### 2. **Health Checks**
```python
class AlertSystemHealthCheck:
    """Comprehensive health monitoring"""
    
    async def check_database_health(self) -> HealthStatus:
        """Check database connectivity and performance"""
        pass
    
    async def check_queue_health(self) -> HealthStatus:
        """Check queue sizes and processing rates"""
        pass
    
    async def check_plugin_health(self) -> HealthStatus:
        """Check all plugins are responsive"""
        pass
    
    async def check_audit_health(self) -> HealthStatus:
        """Check audit service is recording events"""
        pass
```

## Implementation Benefits

### 🚀 **Universal Coverage**
- **ANY Event Type**: Earnings, grades, prices, news, custom events
- **ANY Entity**: Stocks, portfolios, markets, sectors
- **ANY Condition**: Simple thresholds to complex multi-factor rules

### 🔧 **Pluggable Architecture**
- **Data Sources**: Easy to add new APIs and data feeds
- **Processors**: Custom event processing logic
- **Evaluators**: Domain-specific alert evaluation
- **Notifications**: Custom channels and formats

### 📊 **Enterprise Features**
- **Audit Trail**: Complete traceability with existing audit service
- **Observability**: Metrics, logs, tracing, health checks
- **Scalability**: Horizontal scaling with queue-based processing
- **Reliability**: Retry mechanisms, dead letter queues, circuit breakers

### 🎯 **Industry Standards**
- **Event Sourcing**: Immutable event log for full history
- **CQRS**: Separate read/write models for performance
- **SOLID Principles**: Maintainable, extensible code
- **Clean Architecture**: Business logic separated from infrastructure

This universal alert system can handle the earnings calendar email you showed, analyst grade changes, price movements, news events, and any future alert type - all with the same pluggable, auditable, observable infrastructure.
