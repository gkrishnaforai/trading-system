-- Add notes and pluggable alerts system
-- PostgreSQL/Supabase compatible

-- Add notes to portfolios
ALTER TABLE portfolios ADD COLUMN IF NOT EXISTS notes TEXT DEFAULT NULL;

-- Add notes to holdings (stock-level notes)
ALTER TABLE holdings ADD COLUMN IF NOT EXISTS notes TEXT DEFAULT NULL;

-- Alert Types table (pluggable alert types)
CREATE TABLE IF NOT EXISTS alert_types (
    alert_type_id VARCHAR(255) PRIMARY KEY,
    name VARCHAR(100) NOT NULL UNIQUE,
    display_name VARCHAR(255) NOT NULL,
    description TEXT,
    plugin_name VARCHAR(100) NOT NULL,
    config_schema JSONB,
    enabled BOOLEAN DEFAULT TRUE,
    subscription_level_required VARCHAR(50) CHECK(subscription_level_required IN ('basic', 'pro', 'elite')),
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- Alerts table (user-configured alerts)
CREATE TABLE IF NOT EXISTS alerts (
    alert_id VARCHAR(255) PRIMARY KEY,
    user_id VARCHAR(255) NOT NULL,
    portfolio_id VARCHAR(255),
    stock_symbol VARCHAR(10),
    alert_type_id VARCHAR(255) NOT NULL,
    name VARCHAR(255) NOT NULL,
    enabled BOOLEAN DEFAULT TRUE,
    config JSONB NOT NULL,
    notification_channels VARCHAR(255) NOT NULL,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE,
    FOREIGN KEY (portfolio_id) REFERENCES portfolios(portfolio_id) ON DELETE CASCADE,
    FOREIGN KEY (alert_type_id) REFERENCES alert_types(alert_type_id),
    CHECK ((portfolio_id IS NOT NULL) OR (stock_symbol IS NOT NULL))
);

-- Alert Notifications table
CREATE TABLE IF NOT EXISTS alert_notifications (
    notification_id VARCHAR(255) PRIMARY KEY,
    alert_id VARCHAR(255) NOT NULL,
    user_id VARCHAR(255) NOT NULL,
    portfolio_id VARCHAR(255),
    stock_symbol VARCHAR(10),
    alert_type_id VARCHAR(255) NOT NULL,
    message TEXT NOT NULL,
    severity VARCHAR(50) CHECK(severity IN ('info', 'warning', 'critical')) DEFAULT 'info',
    channel VARCHAR(50) NOT NULL CHECK(channel IN ('email', 'sms', 'push', 'webhook')),
    status VARCHAR(50) CHECK(status IN ('pending', 'sent', 'failed')) DEFAULT 'pending',
    sent_at TIMESTAMP,
    error_message TEXT,
    metadata JSONB,
    created_at TIMESTAMP DEFAULT NOW(),
    FOREIGN KEY (alert_id) REFERENCES alerts(alert_id) ON DELETE CASCADE,
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE,
    FOREIGN KEY (portfolio_id) REFERENCES portfolios(portfolio_id) ON DELETE SET NULL,
    FOREIGN KEY (alert_type_id) REFERENCES alert_types(alert_type_id)
);

-- Notification Channels table
CREATE TABLE IF NOT EXISTS notification_channels (
    channel_id VARCHAR(255) PRIMARY KEY,
    user_id VARCHAR(255) NOT NULL,
    channel_type VARCHAR(50) NOT NULL CHECK(channel_type IN ('email', 'sms', 'push', 'webhook')),
    address TEXT NOT NULL,
    verified BOOLEAN DEFAULT FALSE,
    enabled BOOLEAN DEFAULT TRUE,
    config JSONB,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
);

-- Create indexes
CREATE INDEX IF NOT EXISTS idx_alerts_user_id ON alerts(user_id);
CREATE INDEX IF NOT EXISTS idx_alerts_portfolio_id ON alerts(portfolio_id);
CREATE INDEX IF NOT EXISTS idx_alerts_stock_symbol ON alerts(stock_symbol);
CREATE INDEX IF NOT EXISTS idx_alert_notifications_alert_id ON alert_notifications(alert_id);
CREATE INDEX IF NOT EXISTS idx_alert_notifications_user_id ON alert_notifications(user_id);
CREATE INDEX IF NOT EXISTS idx_notification_channels_user_id ON notification_channels(user_id);

