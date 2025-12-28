-- Add notes and pluggable alerts system
-- Industry Standard: Extensible alert system with plugin support
-- Supports: Email, SMS, and future alert types via configuration/DB

-- Add notes to portfolios
ALTER TABLE portfolios ADD COLUMN notes TEXT DEFAULT NULL;

-- Add notes to holdings (stock-level notes)
ALTER TABLE holdings ADD COLUMN notes TEXT DEFAULT NULL;

-- Alert Types table (pluggable alert types)
-- New alert types can be added via DB or configuration without code changes
CREATE TABLE IF NOT EXISTS alert_types (
    alert_type_id TEXT PRIMARY KEY,
    name TEXT NOT NULL UNIQUE, -- e.g., 'price_threshold', 'signal_change', 'volume_spike'
    display_name TEXT NOT NULL, -- User-friendly name
    description TEXT,
    plugin_name TEXT NOT NULL, -- Plugin that handles this alert type
    config_schema JSON, -- JSON schema for alert configuration
    enabled BOOLEAN DEFAULT TRUE,
    subscription_level_required TEXT CHECK(subscription_level_required IN ('basic', 'pro', 'elite')),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Alerts table (user-configured alerts)
-- Supports portfolio-level and stock-level alerts
CREATE TABLE IF NOT EXISTS alerts (
    alert_id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    portfolio_id TEXT, -- NULL if stock-level alert
    stock_symbol TEXT, -- NULL if portfolio-level alert
    alert_type_id TEXT NOT NULL,
    name TEXT NOT NULL, -- User-defined alert name
    enabled BOOLEAN DEFAULT TRUE,
    config JSON NOT NULL, -- Alert-specific configuration (thresholds, conditions, etc.)
    notification_channels TEXT NOT NULL, -- Comma-separated: 'email,sms' or 'email' or 'sms'
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE,
    FOREIGN KEY (portfolio_id) REFERENCES portfolios(portfolio_id) ON DELETE CASCADE,
    FOREIGN KEY (alert_type_id) REFERENCES alert_types(alert_type_id),
    -- Ensure either portfolio_id or stock_symbol is set
    CHECK ((portfolio_id IS NOT NULL) OR (stock_symbol IS NOT NULL))
);

-- Alert Notifications table (history of triggered alerts)
CREATE TABLE IF NOT EXISTS alert_notifications (
    notification_id TEXT PRIMARY KEY,
    alert_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    portfolio_id TEXT,
    stock_symbol TEXT,
    alert_type_id TEXT NOT NULL,
    message TEXT NOT NULL,
    severity TEXT CHECK(severity IN ('info', 'warning', 'critical')) DEFAULT 'info',
    channel TEXT NOT NULL CHECK(channel IN ('email', 'sms', 'push', 'webhook')),
    status TEXT CHECK(status IN ('pending', 'sent', 'failed')) DEFAULT 'pending',
    sent_at TIMESTAMP,
    error_message TEXT,
    metadata JSON, -- Additional context (price, signal, etc.)
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (alert_id) REFERENCES alerts(alert_id) ON DELETE CASCADE,
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE,
    FOREIGN KEY (portfolio_id) REFERENCES portfolios(portfolio_id) ON DELETE SET NULL,
    FOREIGN KEY (alert_type_id) REFERENCES alert_types(alert_type_id)
);

-- Notification Channels table (user notification preferences)
CREATE TABLE IF NOT EXISTS notification_channels (
    channel_id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    channel_type TEXT NOT NULL CHECK(channel_type IN ('email', 'sms', 'push', 'webhook')),
    address TEXT NOT NULL, -- email address, phone number, webhook URL, etc.
    verified BOOLEAN DEFAULT FALSE,
    enabled BOOLEAN DEFAULT TRUE,
    config JSON, -- Channel-specific config (e.g., SMTP settings, API keys)
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE,
    UNIQUE(user_id, channel_type, address)
);

-- Create indexes for performance
CREATE INDEX IF NOT EXISTS idx_alerts_user_id ON alerts(user_id);
CREATE INDEX IF NOT EXISTS idx_alerts_portfolio_id ON alerts(portfolio_id);
CREATE INDEX IF NOT EXISTS idx_alerts_stock_symbol ON alerts(stock_symbol);
CREATE INDEX IF NOT EXISTS idx_alerts_type_id ON alerts(alert_type_id);
CREATE INDEX IF NOT EXISTS idx_alerts_enabled ON alerts(enabled);
CREATE INDEX IF NOT EXISTS idx_alert_notifications_alert_id ON alert_notifications(alert_id);
CREATE INDEX IF NOT EXISTS idx_alert_notifications_user_id ON alert_notifications(user_id);
CREATE INDEX IF NOT EXISTS idx_alert_notifications_status ON alert_notifications(status);
CREATE INDEX IF NOT EXISTS idx_alert_notifications_created_at ON alert_notifications(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_notification_channels_user_id ON notification_channels(user_id);
CREATE INDEX IF NOT EXISTS idx_notification_channels_type ON notification_channels(channel_type);

-- Insert default alert types (can be extended via DB or config)
INSERT INTO alert_types (alert_type_id, name, display_name, description, plugin_name, config_schema, subscription_level_required)
VALUES
    ('price_threshold', 'price_threshold', 'Price Threshold', 'Alert when stock price crosses a threshold', 'email_alert', '{"type": "object", "properties": {"threshold": {"type": "number"}, "direction": {"type": "string", "enum": ["above", "below"]}}}', 'basic'),
    ('signal_change', 'signal_change', 'Signal Change', 'Alert when trading signal changes (buy/sell/hold)', 'email_alert', '{"type": "object", "properties": {"from_signal": {"type": "string"}, "to_signal": {"type": "string"}}}', 'pro'),
    ('volume_spike', 'volume_spike', 'Volume Spike', 'Alert when trading volume exceeds threshold', 'email_alert', '{"type": "object", "properties": {"multiplier": {"type": "number", "default": 2.0}}}', 'pro'),
    ('rsi_extreme', 'rsi_extreme', 'RSI Extreme', 'Alert when RSI reaches overbought/oversold levels', 'email_alert', '{"type": "object", "properties": {"level": {"type": "number", "default": 70}, "direction": {"type": "string", "enum": ["overbought", "oversold"]}}}', 'pro'),
    ('macd_crossover', 'macd_crossover', 'MACD Crossover', 'Alert on MACD line crossing signal line', 'email_alert', '{"type": "object", "properties": {"direction": {"type": "string", "enum": ["bullish", "bearish"]}}}', 'pro'),
    ('portfolio_risk', 'portfolio_risk', 'Portfolio Risk', 'Alert when portfolio risk exceeds threshold', 'email_alert', '{"type": "object", "properties": {"risk_threshold": {"type": "number"}}}', 'elite')
ON CONFLICT (alert_type_id) DO NOTHING;

