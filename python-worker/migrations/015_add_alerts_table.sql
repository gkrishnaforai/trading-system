-- Add alerts table for rating alert system
-- This migration creates the missing alerts table that works with existing schema

-- Alerts table (user-configured alerts)
-- Supports portfolio-level and stock-level alerts
CREATE TABLE IF NOT EXISTS alerts (
    alert_id TEXT PRIMARY KEY,
    user_id UUID NOT NULL,
    portfolio_id UUID, -- NULL if stock-level alert
    stock_symbol TEXT, -- NULL if portfolio-level alert
    alert_type_id TEXT NOT NULL,
    name TEXT NOT NULL, -- User-defined alert name
    enabled BOOLEAN DEFAULT TRUE,
    config JSON NOT NULL, -- Alert-specific configuration (thresholds, conditions, etc.)
    notification_channels TEXT NOT NULL, -- Comma-separated: 'email,sms' or 'email' or 'sms'
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (portfolio_id) REFERENCES portfolios(id) ON DELETE CASCADE,
    FOREIGN KEY (alert_type_id) REFERENCES alert_types(alert_type_id),
    -- Ensure either portfolio_id or stock_symbol is set
    CHECK ((portfolio_id IS NOT NULL) OR (stock_symbol IS NOT NULL))
);

-- Alert Notifications table (history of triggered alerts)
CREATE TABLE IF NOT EXISTS alert_notifications (
    notification_id TEXT PRIMARY KEY,
    alert_id TEXT NOT NULL,
    user_id UUID NOT NULL,
    triggered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    message TEXT NOT NULL,
    details JSON, -- Additional details about the alert trigger
    status TEXT DEFAULT 'pending' CHECK(status IN ('pending', 'sent', 'failed')),
    sent_at TIMESTAMP,
    error_message TEXT,
    FOREIGN KEY (alert_id) REFERENCES alerts(alert_id) ON DELETE CASCADE,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

-- Notification Channels table
CREATE TABLE IF NOT EXISTS notification_channels (
    channel_id TEXT PRIMARY KEY,
    user_id UUID NOT NULL,
    channel_type TEXT NOT NULL CHECK(channel_type IN ('email', 'sms', 'webhook', 'push')),
    channel_address TEXT NOT NULL, -- Email address, phone number, webhook URL, etc.
    is_verified BOOLEAN DEFAULT FALSE,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_alerts_user_id ON alerts(user_id);
CREATE INDEX IF NOT EXISTS idx_alerts_stock_symbol ON alerts(stock_symbol);
CREATE INDEX IF NOT EXISTS idx_alerts_alert_type_id ON alerts(alert_type_id);
CREATE INDEX IF NOT EXISTS idx_alerts_enabled ON alerts(enabled);
CREATE INDEX IF NOT EXISTS idx_alert_notifications_alert_id ON alert_notifications(alert_id);
CREATE INDEX IF NOT EXISTS idx_alert_notifications_user_id ON alert_notifications(user_id);
CREATE INDEX IF NOT EXISTS idx_alert_notifications_triggered_at ON alert_notifications(triggered_at);
CREATE INDEX IF NOT EXISTS idx_notification_channels_user_id ON notification_channels(user_id);
CREATE INDEX IF NOT EXISTS idx_notification_channels_type ON notification_channels(channel_type);

-- Insert rating-related alert types
INSERT INTO alert_types (alert_type_id, name, display_name, description, plugin_name, priority_level, category, is_active) VALUES
('rating_change', 'Rating Change', 'Rating Change', 'Alert when analyst ratings change', 'rating_alerts', 'MEDIUM', 'rating', TRUE),
('price_target_change', 'Price Target Change', 'Price Target Change', 'Alert when consensus price targets change', 'rating_alerts', 'MEDIUM', 'rating', TRUE),
('consensus_alert', 'Consensus Alert', 'Consensus Alert', 'Alert when consensus reaches specific levels', 'rating_alerts', 'MEDIUM', 'rating', TRUE),
('earnings_alert', 'Earnings Alert', 'Earnings Alert', 'Alert for earnings announcements and surprises', 'rating_alerts', 'MEDIUM', 'earnings', TRUE)
ON CONFLICT (alert_type_id) DO NOTHING;
