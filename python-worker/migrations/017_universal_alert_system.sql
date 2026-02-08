-- ========================================
-- UNIVERSAL ALERT SYSTEM - Industry Standard
-- Migration: 017_universal_alert_system.sql
-- Supports ANY alert type with pluggable, auditable, observable architecture
-- Follows SOLID principles, DRY, Event Sourcing, CQRS patterns
-- ========================================

-- Enhance existing stocks table for alert support
ALTER TABLE stocks 
ADD COLUMN IF NOT EXISTS alert_metadata JSONB DEFAULT '{}',
ADD COLUMN IF NOT EXISTS last_alert_check TIMESTAMPTZ,
ADD COLUMN IF NOT EXISTS alert_subscription_count INTEGER DEFAULT 0,
ADD COLUMN IF NOT EXISTS alert_events_count INTEGER DEFAULT 0,
ADD COLUMN IF NOT EXISTS alert_preferences JSONB DEFAULT '{}';

-- Create indexes for alert performance
CREATE INDEX IF NOT EXISTS idx_stocks_alert_check ON stocks(last_alert_check) WHERE last_alert_check IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_stocks_alert_metadata ON stocks USING GIN(alert_metadata);
CREATE INDEX IF NOT EXISTS idx_stocks_alert_preferences ON stocks USING GIN(alert_preferences);
CREATE INDEX IF NOT EXISTS idx_stocks_subscription_count ON stocks(alert_subscription_count) WHERE alert_subscription_count > 0;

-- Universal events table - CORE of the universal alert system
CREATE TABLE IF NOT EXISTS universal_events (
    event_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    event_type VARCHAR(50) NOT NULL,
    entity_type VARCHAR(20) NOT NULL CHECK (entity_type IN ('stock', 'portfolio', 'market', 'user', 'system')),
    entity_id VARCHAR(50) NOT NULL,
    
    -- Event data (flexible schema for ANY event type)
    event_data JSONB NOT NULL,
    previous_data JSONB,
    change_metadata JSONB,
    
    -- Temporal data
    event_timestamp TIMESTAMPTZ NOT NULL,
    detected_at TIMESTAMPTZ DEFAULT NOW(),
    processed_at TIMESTAMPTZ,
    
    -- Source and provenance
    data_source VARCHAR(50) NOT NULL,
    source_id VARCHAR(100),
    source_version VARCHAR(20),
    confidence_score DECIMAL(3,2) DEFAULT 1.0 CHECK (confidence_score BETWEEN 0.0 AND 1.0),
    
    -- Processing metadata
    processing_status VARCHAR(20) DEFAULT 'pending' CHECK (processing_status IN ('pending', 'processing', 'completed', 'failed', 'cancelled', 'retry')),
    error_message TEXT,
    error_details JSONB,
    retry_count INTEGER DEFAULT 0,
    max_retries INTEGER DEFAULT 3,
    priority INTEGER DEFAULT 3 CHECK (priority BETWEEN 1 AND 5),
    
    -- Audit and traceability
    correlation_id VARCHAR(50),
    parent_event_id UUID REFERENCES universal_events(event_id),
    causation_id VARCHAR(50), -- What caused this event
    command_id VARCHAR(50), -- Command that generated this event
    
    -- Metadata
    tags TEXT[],
    version INTEGER DEFAULT 1,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    
    -- Constraints
    CHECK (event_timestamp <= detected_at),
    CHECK (retry_count >= 0 AND retry_count <= max_retries)
);

-- Universal alert definitions - User-configured alerts for ANY event type
CREATE TABLE IF NOT EXISTS universal_alerts (
    alert_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    alert_name VARCHAR(200) NOT NULL,
    alert_type VARCHAR(50) NOT NULL,
    alert_category VARCHAR(50) DEFAULT 'custom',
    
    -- Target criteria (universal filtering)
    entity_filters JSONB NOT NULL DEFAULT '{}',
    event_filters JSONB NOT NULL DEFAULT '{}',
    
    -- Advanced conditions and logic
    trigger_conditions JSONB NOT NULL DEFAULT '{}',
    suppression_rules JSONB DEFAULT '{}',
    escalation_rules JSONB DEFAULT '{}',
    
    -- Configuration
    notification_config JSONB DEFAULT '{}',
    template_config JSONB DEFAULT '{}',
    priority_level INTEGER DEFAULT 3 CHECK (priority_level BETWEEN 1 AND 5),
    is_active BOOLEAN DEFAULT TRUE,
    is_test BOOLEAN DEFAULT FALSE,
    
    -- Scheduling and windows
    schedule_config JSONB DEFAULT '{}',
    time_windows JSONB DEFAULT '{}',
    timezone VARCHAR(50) DEFAULT 'UTC',
    
    -- Statistics and performance
    trigger_count INTEGER DEFAULT 0,
    success_count INTEGER DEFAULT 0,
    failure_count INTEGER DEFAULT 0,
    last_triggered_at TIMESTAMPTZ,
    last_success_at TIMESTAMPTZ,
    last_failure_at TIMESTAMPTZ,
    avg_trigger_duration_ms INTEGER,
    
    -- Rate limiting
    rate_limit_config JSONB DEFAULT '{}',
    current_rate_usage JSONB DEFAULT '{}',
    
    -- Audit fields
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    created_by UUID REFERENCES users(id),
    updated_by UUID REFERENCES users(id),
    
    -- Versioning for audit trail
    version INTEGER DEFAULT 1,
    
    -- Constraints
    CHECK (trigger_count >= 0),
    CHECK (success_count >= 0),
    CHECK (failure_count >= 0),
    CHECK (version >= 1)
);

-- Universal alert events - Triggered alert instances
CREATE TABLE IF NOT EXISTS universal_alert_events (
    event_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    alert_id UUID NOT NULL REFERENCES universal_alerts(alert_id) ON DELETE CASCADE,
    universal_event_id UUID NOT NULL REFERENCES universal_events(event_id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    
    -- Evaluation metadata
    match_score DECIMAL(5,2) CHECK (match_score BETWEEN 0.0 AND 100.0),
    trigger_reason TEXT NOT NULL,
    trigger_details JSONB DEFAULT '{}',
    urgency_level VARCHAR(20) DEFAULT 'medium' CHECK (urgency_level IN ('low', 'medium', 'high', 'critical')),
    
    -- Processing status and timing
    status VARCHAR(20) DEFAULT 'pending' CHECK (status IN ('pending', 'processing', 'sent', 'failed', 'cancelled', 'suppressed')),
    processed_at TIMESTAMPTZ,
    sent_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    processing_duration_ms INTEGER,
    
    -- Error handling
    error_message TEXT,
    error_details JSONB,
    retry_count INTEGER DEFAULT 0,
    max_retries INTEGER DEFAULT 3,
    
    -- Notification tracking
    notification_count INTEGER DEFAULT 0,
    successful_notifications INTEGER DEFAULT 0,
    failed_notifications INTEGER DEFAULT 0,
    
    -- Audit and traceability
    correlation_id VARCHAR(50),
    session_id VARCHAR(50),
    
    -- Metadata
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    
    -- Constraints
    CHECK (notification_count >= 0),
    CHECK (successful_notifications >= 0),
    CHECK (failed_notifications >= 0),
    CHECK (retry_count >= 0 AND retry_count <= max_retries),
    
    -- Unique constraint to prevent duplicate alerts
    UNIQUE(alert_id, universal_event_id)
);

-- Enhanced notification queue with universal support
CREATE TABLE IF NOT EXISTS universal_notification_queue (
    queue_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    alert_event_id UUID NOT NULL REFERENCES universal_alert_events(event_id) ON DELETE CASCADE,
    
    -- Notification details
    channel_type VARCHAR(20) NOT NULL CHECK (channel_type IN ('email', 'sms', 'push', 'webhook', 'slack', 'teams', 'custom')),
    recipient VARCHAR(500) NOT NULL,
    recipient_type VARCHAR(20) DEFAULT 'user' CHECK (recipient_type IN ('user', 'system', 'external')),
    
    -- Message content
    subject VARCHAR(500),
    message_body TEXT NOT NULL,
    html_body TEXT,
    template_name VARCHAR(100),
    template_data JSONB DEFAULT '{}',
    attachments JSONB DEFAULT '[]',
    
    -- Delivery configuration
    delivery_config JSONB DEFAULT '{}',
    priority INTEGER DEFAULT 3 CHECK (priority BETWEEN 1 AND 5),
    send_after TIMESTAMPTZ DEFAULT NOW(),
    expire_at TIMESTAMPTZ,
    
    -- Status and tracking
    status VARCHAR(20) DEFAULT 'pending' CHECK (status IN ('pending', 'processing', 'sent', 'failed', 'cancelled', 'expired')),
    attempts INTEGER DEFAULT 0,
    max_attempts INTEGER DEFAULT 3,
    last_attempt_at TIMESTAMPTZ,
    next_attempt_at TIMESTAMPTZ DEFAULT NOW(),
    sent_at TIMESTAMPTZ,
    delivered_at TIMESTAMPTZ,
    
    -- Error handling
    error_message TEXT,
    error_details JSONB,
    error_code VARCHAR(50),
    
    -- External tracking
    external_id VARCHAR(100), -- Provider-specific message ID
    delivery_receipt JSONB,
    
    -- Audit fields
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    
    -- Constraints
    CHECK (attempts >= 0 AND attempts <= max_attempts),
    CHECK (send_after <= expire_at OR expire_at IS NULL)
);

-- Unified audit trail for ALL alert system operations
CREATE TABLE IF NOT EXISTS alert_audit_trail (
    audit_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    
    -- Entity information
    entity_type VARCHAR(20) NOT NULL CHECK (entity_type IN ('alert', 'event', 'notification', 'job', 'plugin', 'user', 'system')),
    entity_id VARCHAR(50) NOT NULL,
    entity_name VARCHAR(200),
    
    -- Operation details
    operation_type VARCHAR(20) NOT NULL CHECK (operation_type IN ('create', 'update', 'delete', 'trigger', 'send', 'process', 'execute', 'configure')),
    operation_data JSONB NOT NULL,
    previous_state JSONB,
    new_state JSONB,
    state_diff JSONB,
    
    -- Execution context
    user_id UUID REFERENCES users(id),
    job_id VARCHAR(50),
    plugin_name VARCHAR(50),
    correlation_id VARCHAR(50),
    session_id VARCHAR(50),
    
    -- Results and performance
    status VARCHAR(20) NOT NULL CHECK (status IN ('started', 'completed', 'failed', 'cancelled', 'timeout')),
    result_data JSONB,
    error_message TEXT,
    error_stack TEXT,
    error_code VARCHAR(50),
    
    -- Timing and performance
    started_at TIMESTAMPTZ NOT NULL,
    completed_at TIMESTAMPTZ,
    duration_ms INTEGER,
    cpu_time_ms INTEGER,
    memory_usage_mb INTEGER,
    
    -- System context
    ip_address INET,
    user_agent TEXT,
    hostname VARCHAR(100),
    process_id INTEGER,
    thread_id VARCHAR(50),
    
    -- Business context
    business_context JSONB DEFAULT '{}',
    impact_level VARCHAR(20) DEFAULT 'low' CHECK (impact_level IN ('low', 'medium', 'high', 'critical')),
    
    -- Metadata
    tags TEXT[],
    version INTEGER DEFAULT 1,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    
    -- Constraints
    CHECK (duration_ms IS NULL OR duration_ms >= 0),
    CHECK (cpu_time_ms IS NULL OR cpu_time_ms >= 0),
    CHECK (memory_usage_mb IS NULL OR memory_usage_mb >= 0),
    CHECK (version >= 1)
);

-- Plugin registry for dynamic plugin management
CREATE TABLE IF NOT EXISTS alert_plugins (
    plugin_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    plugin_name VARCHAR(100) NOT NULL UNIQUE,
    plugin_type VARCHAR(50) NOT NULL CHECK (plugin_type IN ('data_source', 'processor', 'evaluator', 'notifier', 'filter')),
    plugin_class VARCHAR(200) NOT NULL,
    
    -- Plugin configuration
    config_schema JSONB NOT NULL,
    default_config JSONB DEFAULT '{}',
    
    -- Capabilities and metadata
    supported_event_types TEXT[],
    supported_alert_types TEXT[],
    version VARCHAR(20) NOT NULL,
    author VARCHAR(100),
    description TEXT,
    
    -- Status and lifecycle
    is_active BOOLEAN DEFAULT TRUE,
    is_builtin BOOLEAN DEFAULT FALSE,
    installed_at TIMESTAMPTZ DEFAULT NOW(),
    last_updated_at TIMESTAMPTZ DEFAULT NOW(),
    
    -- Dependencies
    dependencies JSONB DEFAULT '[]',
    conflicts JSONB DEFAULT '[]',
    
    -- Runtime information
    runtime_config JSONB DEFAULT '{}',
    health_status VARCHAR(20) DEFAULT 'unknown' CHECK (health_status IN ('healthy', 'degraded', 'unhealthy', 'unknown')),
    last_health_check TIMESTAMPTZ,
    
    -- Audit fields
    created_by UUID REFERENCES users(id),
    updated_by UUID REFERENCES users(id),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Performance indexes for universal events
CREATE INDEX IF NOT EXISTS idx_universal_events_type_entity ON universal_events(event_type, entity_type, entity_id);
CREATE INDEX IF NOT EXISTS idx_universal_events_timestamp ON universal_events(event_timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_universal_events_status ON universal_events(processing_status, detected_at);
CREATE INDEX IF NOT EXISTS idx_universal_events_source ON universal_events(data_source, detected_at);
CREATE INDEX IF NOT EXISTS idx_universal_events_correlation ON universal_events(correlation_id);
CREATE INDEX IF NOT EXISTS idx_universal_events_parent ON universal_events(parent_event_id);
CREATE INDEX IF NOT EXISTS idx_universal_events_data ON universal_events USING GIN(event_data);
CREATE INDEX IF NOT EXISTS idx_universal_events_change ON universal_events USING GIN(change_metadata);

-- Performance indexes for universal alerts
CREATE INDEX IF NOT EXISTS idx_universal_alerts_user_active ON universal_alerts(user_id, is_active) WHERE is_active = true;
CREATE INDEX IF NOT EXISTS idx_universal_alerts_type ON universal_alerts(alert_type, alert_category);
CREATE INDEX IF NOT EXISTS idx_universal_alerts_triggered ON universal_alerts(last_triggered_at DESC) WHERE last_triggered_at IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_universal_alerts_filters ON universal_alerts USING GIN(entity_filters);
CREATE INDEX IF NOT EXISTS idx_universal_alerts_conditions ON universal_alerts USING GIN(trigger_conditions);

-- Performance indexes for alert events
CREATE INDEX IF NOT EXISTS idx_universal_alert_events_status ON universal_alert_events(status, created_at);
CREATE INDEX IF NOT EXISTS idx_universal_alert_events_user ON universal_alert_events(user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_universal_alert_events_urgency ON universal_alert_events(urgency_level, status);
CREATE INDEX IF NOT EXISTS idx_universal_alert_events_correlation ON universal_alert_events(correlation_id);

-- Performance indexes for notification queue
CREATE INDEX IF NOT EXISTS idx_universal_notification_status ON universal_notification_queue(status, next_attempt_at);
CREATE INDEX IF NOT EXISTS idx_universal_notification_channel ON universal_notification_queue(channel_type, status);
CREATE INDEX IF NOT EXISTS idx_universal_notification_priority ON universal_notification_queue(priority DESC, send_after);
CREATE INDEX IF NOT EXISTS idx_universal_notification_recipient ON universal_notification_queue(recipient, channel_type);

-- Performance indexes for audit trail
CREATE INDEX IF NOT EXISTS idx_alert_audit_entity ON alert_audit_trail(entity_type, entity_id, operation_type);
CREATE INDEX IF NOT EXISTS idx_alert_audit_user ON alert_audit_trail(user_id, started_at DESC);
CREATE INDEX IF NOT EXISTS idx_alert_audit_correlation ON alert_audit_trail(correlation_id);
CREATE INDEX IF NOT EXISTS idx_alert_audit_status ON alert_audit_trail(status, started_at DESC);
CREATE INDEX IF NOT EXISTS idx_alert_audit_timing ON alert_audit_trail(started_at, duration_ms);
CREATE INDEX IF NOT EXISTS idx_alert_audit_impact ON alert_audit_trail(impact_level, status);

-- Performance indexes for plugins
CREATE INDEX IF NOT EXISTS idx_alert_plugins_type ON alert_plugins(plugin_type, is_active);
CREATE INDEX IF NOT EXISTS idx_alert_plugins_health ON alert_plugins(health_status, last_health_check);

-- Insert default plugin configurations
INSERT INTO alert_plugins (plugin_name, plugin_type, plugin_class, config_schema, default_config, supported_event_types, supported_alert_types, version, is_builtin, author) VALUES
('earnings_calendar', 'data_source', 'EarningsCalendarPlugin', 
 '{"type": "object", "properties": {"api_key": {"type": "string"}, "sources": {"type": "array"}}}',
 '{"sources": ["fmp", "alpha_vantage"], "update_frequency_minutes": 60}',
 ARRAY['earnings_date', 'earnings_surprise', 'guidance_update'],
 ARRAY['earnings', 'earnings_preview', 'earnings_surprise'],
 '1.0.0', true, 'System'),
 
('analyst_grades', 'data_source', 'AnalystGradesPlugin',
 '{"type": "object", "properties": {"api_key": {"type": "string"}, "tier_1_firms_only": {"type": "boolean"}}}',
 '{"tier_1_firms_only": false, "update_frequency_minutes": 15}',
 ARRAY['grade_change', 'consensus_update', 'price_target_change'],
 ARRAY['grade_change', 'consensus_alert', 'price_target_change'],
 '1.0.0', true, 'System'),
 
('price_movements', 'data_source', 'PriceMovementsPlugin',
 '{"type": "object", "properties": {"symbols": {"type": "array"}, "threshold_percent": {"type": "number"}}}',
 '{"threshold_percent": 5.0, "update_frequency_minutes": 5}',
 ARRAY['price_change', 'volume_spike', 'volatility_breakout'],
 ARRAY['price_alert', 'volume_alert', 'volatility_alert'],
 '1.0.0', true, 'System'),
 
('news_events', 'data_source', 'NewsEventsPlugin',
 '{"type": "object", "properties": {"sources": {"type": "array"}, "keywords": {"type": "array"}}}',
 '{"sources": ["newsapi", "benzinga"], "sentiment_threshold": 0.7}',
 ARRAY['news_breaking', 'sentiment_change', 'sec_filing'],
 ARRAY['news_alert', 'sentiment_alert', 'sec_filing_alert'],
 '1.0.0', true, 'System'),
 
('email_notifier', 'notifier', 'EmailNotificationPlugin',
 '{"type": "object", "properties": {"smtp_host": {"type": "string"}, "smtp_port": {"type": "integer"}}}',
 '{"smtp_host": "localhost", "smtp_port": 587, "templates": ["default", "earnings", "grades"]}',
 ARRAY[]::TEXT[],
 ARRAY['email'],
 '1.0.0', true, 'System')
ON CONFLICT (plugin_name) DO NOTHING;

-- Create trigger functions for updated_at
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Apply triggers to tables with updated_at columns
CREATE TRIGGER update_universal_events_updated_at BEFORE UPDATE ON universal_events FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
CREATE TRIGGER update_universal_alerts_updated_at BEFORE UPDATE ON universal_alerts FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
CREATE TRIGGER update_universal_alert_events_updated_at BEFORE UPDATE ON universal_alert_events FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
CREATE TRIGGER update_universal_notification_queue_updated_at BEFORE UPDATE ON universal_notification_queue FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
CREATE TRIGGER update_alert_plugins_updated_at BEFORE UPDATE ON alert_plugins FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- Create function for audit trail logging
CREATE OR REPLACE FUNCTION log_alert_audit_operation()
RETURNS TRIGGER AS $$
BEGIN
    INSERT INTO alert_audit_trail (
        entity_type, entity_id, entity_name, operation_type, operation_data,
        previous_state, new_state, status, started_at, completed_at, duration_ms,
        user_id, correlation_id, session_id
    ) VALUES (
        TG_TABLE_NAME,
        COALESCE(NEW.id::TEXT, OLD.id::TEXT),
        COALESCE(NEW.name, OLD.name, TG_TABLE_NAME || '_' || COALESCE(NEW.id::TEXT, OLD.id::TEXT)),
        CASE TG_OP
            WHEN 'INSERT' THEN 'create'
            WHEN 'UPDATE' THEN 'update'
            WHEN 'DELETE' THEN 'delete'
            ELSE 'unknown'
        END,
        CASE TG_OP
            WHEN 'INSERT' THEN row_to_json(NEW)
            WHEN 'UPDATE' THEN json_build_object('new', row_to_json(NEW), 'old', row_to_json(OLD))
            WHEN 'DELETE' THEN row_to_json(OLD)
            ELSE '{}'
        END,
        CASE TG_OP WHEN 'UPDATE' THEN row_to_json(OLD) ELSE NULL END,
        CASE TG_OP WHEN 'INSERT' OR 'UPDATE' THEN row_to_json(NEW) ELSE NULL END,
        CASE TG_OP WHEN 'INSERT' OR 'UPDATE' THEN 'completed' ELSE 'completed' END,
        NOW(),
        NOW(),
        0,
        COALESCE(NEW.user_id, OLD.user_id),
        COALESCE(NEW.correlation_id, OLD.correlation_id),
        COALESCE(NEW.session_id, OLD.session_id)
    );
    
    RETURN COALESCE(NEW, OLD);
END;
$$ language 'plpgsql';

-- Apply audit triggers (optional - can be enabled per table)
-- CREATE TRIGGER audit_universal_alerts AFTER INSERT OR UPDATE OR DELETE ON universal_alerts FOR EACH ROW EXECUTE FUNCTION log_alert_audit_operation();
-- CREATE TRIGGER audit_universal_alert_events AFTER INSERT OR UPDATE OR DELETE ON universal_alert_events FOR EACH ROW EXECUTE FUNCTION log_alert_audit_operation();

-- Create view for active alert statistics
CREATE OR REPLACE VIEW active_alert_statistics AS
SELECT 
    alert_type,
    COUNT(*) as total_alerts,
    COUNT(*) FILTER (WHERE is_active = true) as active_alerts,
    COUNT(*) FILTER (WHERE last_triggered_at > NOW() - INTERVAL '24 hours') as alerts_triggered_24h,
    AVG(trigger_count) as avg_trigger_count,
    MAX(last_triggered_at) as last_trigger_time
FROM universal_alerts
GROUP BY alert_type;

-- Create view for event processing statistics
CREATE OR REPLACE VIEW event_processing_statistics AS
SELECT 
    event_type,
    data_source,
    COUNT(*) as total_events,
    COUNT(*) FILTER (WHERE processing_status = 'completed') as completed_events,
    COUNT(*) FILTER (WHERE processing_status = 'failed') as failed_events,
    COUNT(*) FILTER (WHERE detected_at > NOW() - INTERVAL '24 hours') as events_24h,
    AVG(EXTRACT(EPOCH FROM (processed_at - detected_at)) * 1000) as avg_processing_latency_ms
FROM universal_events
WHERE detected_at > NOW() - INTERVAL '7 days'
GROUP BY event_type, data_source;

-- Create view for notification delivery statistics
CREATE OR REPLACE VIEW notification_delivery_statistics AS
SELECT 
    channel_type,
    status,
    COUNT(*) as total_notifications,
    COUNT(*) FILTER (WHERE created_at > NOW() - INTERVAL '24 hours') as notifications_24h,
    AVG(attempts) as avg_attempts,
    COUNT(*) FILTER (WHERE status = 'sent') / COUNT(*) * 100 as success_rate
FROM universal_notification_queue
WHERE created_at > NOW() - INTERVAL '7 days'
GROUP BY channel_type, status;

COMMENT ON TABLE universal_events IS 'Core table for all events in the universal alert system - supports ANY event type';
COMMENT ON TABLE universal_alerts IS 'User-configured alerts for ANY event type with universal filtering';
COMMENT ON TABLE universal_alert_events IS 'Triggered alert instances linking alerts to events';
COMMENT ON TABLE universal_notification_queue IS 'Unified notification queue for all channels with enhanced tracking';
COMMENT ON TABLE alert_audit_trail IS 'Comprehensive audit trail for all alert system operations';
COMMENT ON TABLE alert_plugins IS 'Registry for pluggable components with dynamic management';

-- Grant permissions (adjust as needed for your setup)
-- GRANT SELECT, INSERT, UPDATE, DELETE ON universal_events TO alert_service;
-- GRANT SELECT, INSERT, UPDATE, DELETE ON universal_alerts TO alert_service;
-- GRANT SELECT, INSERT, UPDATE, DELETE ON universal_alert_events TO alert_service;
-- GRANT SELECT, INSERT, UPDATE, DELETE ON universal_notification_queue TO notification_service;
-- GRANT SELECT, INSERT, UPDATE, DELETE ON alert_audit_trail TO audit_service;
