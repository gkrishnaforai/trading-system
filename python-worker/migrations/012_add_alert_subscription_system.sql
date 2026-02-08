-- ========================================
-- ALERT SUBSCRIPTION SYSTEM
-- Migration: 012_add_alert_subscription_system.sql
-- Configurable alert subscriptions for scalable alert management
-- ========================================

-- Alert types configuration
CREATE TABLE IF NOT EXISTS alert_types (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    alert_type VARCHAR(50) UNIQUE NOT NULL,
    name VARCHAR(100) NOT NULL,
    description TEXT,
    default_config JSONB DEFAULT '{}',
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    
    CONSTRAINT valid_alert_type CHECK (alert_type ~ '^[a-z_]+$')
);

-- Alert subscription configuration
CREATE TABLE IF NOT EXISTS alert_subscriptions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    symbol VARCHAR(10) NOT NULL REFERENCES stocks(symbol) ON DELETE CASCADE,
    alert_type VARCHAR(50) NOT NULL,
    enabled BOOLEAN DEFAULT TRUE,
    priority INTEGER DEFAULT 2 CHECK (priority BETWEEN 1 AND 5),
    config JSONB DEFAULT '{}',
    last_processed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    
    UNIQUE(symbol, alert_type),
    CONSTRAINT valid_subscription CHECK (
        alert_type IN (SELECT alert_type FROM alert_types WHERE is_active = TRUE)
    )
);

-- User-specific alert preferences
CREATE TABLE IF NOT EXISTS user_alert_preferences (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id VARCHAR(100) NOT NULL,
    symbol VARCHAR(10) NOT NULL REFERENCES stocks(symbol) ON DELETE CASCADE,
    alert_type VARCHAR(50) NOT NULL,
    enabled BOOLEAN DEFAULT TRUE,
    priority INTEGER DEFAULT 2 CHECK (priority BETWEEN 1 AND 5),
    notification_channels JSONB DEFAULT '["email"]',
    custom_config JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    
    UNIQUE(user_id, symbol, alert_type),
    CONSTRAINT valid_user_subscription CHECK (
        alert_type IN (SELECT alert_type FROM alert_types WHERE is_active = TRUE)
    )
);

-- Alert processing queue for efficient batch processing
CREATE TABLE IF NOT EXISTS alert_processing_queue (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    symbol VARCHAR(10) NOT NULL REFERENCES stocks(symbol) ON DELETE CASCADE,
    alert_type VARCHAR(50) NOT NULL,
    priority INTEGER DEFAULT 2 CHECK (priority BETWEEN 1 AND 5),
    payload JSONB NOT NULL,
    scheduled_at TIMESTAMPTZ DEFAULT NOW(),
    processed_at TIMESTAMPTZ,
    attempts INTEGER DEFAULT 0,
    max_attempts INTEGER DEFAULT 3,
    status VARCHAR(20) DEFAULT 'pending' CHECK (status IN ('pending', 'processing', 'completed', 'failed')),
    error_message TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    
    CONSTRAINT valid_queue_alert_type CHECK (
        alert_type IN (SELECT alert_type FROM alert_types WHERE is_active = TRUE)
    )
);

-- Indexes for performance
CREATE INDEX idx_alert_subscriptions_symbol_type ON alert_subscriptions(symbol, alert_type);
CREATE INDEX idx_alert_subscriptions_enabled ON alert_subscriptions(enabled) WHERE enabled = TRUE;
CREATE INDEX idx_alert_subscriptions_priority ON alert_subscriptions(priority);
CREATE INDEX idx_user_alert_preferences_user ON user_alert_preferences(user_id);
CREATE INDEX idx_user_alert_preferences_symbol_type ON user_alert_preferences(symbol, alert_type);
CREATE INDEX idx_alert_queue_status_scheduled ON alert_processing_queue(status, scheduled_at);
CREATE INDEX idx_alert_queue_priority ON alert_processing_queue(priority DESC, scheduled_at);

-- Insert default alert types
INSERT INTO alert_types (alert_type, name, description, default_config) VALUES
('rating_updates', 'Rating Updates', 'Analyst rating changes and consensus updates', '{
    "min_consensus_change": 0.3,
    "tier_1_firms_only": false,
    "include_price_targets": true,
    "notification_delay_minutes": 5
}'),
('price_target_updates', 'Price Target Updates', 'Consensus price target changes', '{
    "min_price_change_percent": 5.0,
    "min_analyst_count": 3,
    "notification_delay_minutes": 10
}'),
('earnings_updates', 'Earnings Updates', 'Earnings announcements and surprises', '{
    "include_pre_announcements": true,
    "include_surprises_only": false,
    "min_surprise_percent": 5.0,
    "notification_delay_minutes": 15
}'),
('volume_alerts', 'Volume Anomalies', 'Unusual trading volume patterns', '{
    "volume_multiplier": 3.0,
    "min_volume": 1000000,
    "lookback_days": 30
}'),
('price_alerts', 'Price Movements', 'Significant price movements', '{
    "price_change_percent": 10.0,
    "min_price": 5.0,
    "volume_confirmation": true
}'),
('news_alerts', 'News & Events', 'Breaking news and significant events', '{
    "sentiment_threshold": 0.7,
    "keywords": ["acquisition", "merger", "fda", "lawsuit"],
    "exclude_routine_news": true
}') ON CONFLICT (alert_type) DO NOTHING;

-- Trigger to update updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Triggers for updated_at
CREATE TRIGGER update_alert_subscriptions_updated_at
    BEFORE UPDATE ON alert_subscriptions
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_user_alert_preferences_updated_at
    BEFORE UPDATE ON user_alert_preferences
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- Views for easy querying
CREATE OR REPLACE VIEW active_alert_subscriptions AS
SELECT 
    s.symbol,
    s.company_name,
    sub.alert_type,
    sub.enabled,
    sub.priority,
    sub.config,
    sub.created_at,
    sub.updated_at
FROM alert_subscriptions sub
JOIN stocks s ON s.symbol = sub.symbol
WHERE sub.enabled = TRUE;

CREATE OR REPLACE VIEW user_alert_summary AS
SELECT 
    u.user_id,
    s.symbol,
    s.company_name,
    at.name as alert_type_name,
    COALESCE(uap.enabled, sub.enabled) as enabled,
    COALESCE(uap.priority, sub.priority) as priority,
    COALESCE(uap.notification_channels, '["email"]') as notification_channels
FROM user_alert_preferences uap
RIGHT JOIN alert_subscriptions sub ON uap.symbol = sub.symbol AND uap.alert_type = sub.alert_type
JOIN stocks s ON s.symbol = sub.symbol
JOIN alert_types at ON at.alert_type = sub.alert_type
WHERE sub.enabled = TRUE OR uap.enabled = TRUE;
