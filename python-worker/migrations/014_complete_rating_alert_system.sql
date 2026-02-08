-- ========================================
-- COMPLETE RATING ALERT SYSTEM
-- Migration: 014_complete_rating_alert_system.sql
-- Extends existing alert system with rating and price target capabilities
-- Follows SOLID principles: Single Responsibility, Open/Closed
-- ========================================

-- Add rating columns to stocks table (if not exists)
ALTER TABLE stocks 
ADD COLUMN IF NOT EXISTS rating VARCHAR(20),
ADD COLUMN IF NOT EXISTS price_target DECIMAL(10,2),
ADD COLUMN IF NOT EXISTS rating_score DECIMAL(4,2),
ADD COLUMN IF NOT EXISTS rating_updated_at TIMESTAMPTZ,
ADD COLUMN IF NOT EXISTS rating_data_source VARCHAR(50) DEFAULT 'fmp';

-- Add indexes for rating performance
CREATE INDEX IF NOT EXISTS idx_stocks_rating ON stocks(rating);
CREATE INDEX IF NOT EXISTS idx_stocks_rating_updated ON stocks(rating_updated_at);
CREATE INDEX IF NOT EXISTS idx_stocks_price_target ON stocks(price_target);

-- Rating change audit log
CREATE TABLE IF NOT EXISTS rating_change_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    symbol VARCHAR(10) NOT NULL REFERENCES stocks(symbol) ON DELETE CASCADE,
    old_rating VARCHAR(20),
    new_rating VARCHAR(20),
    old_price_target DECIMAL(10,2),
    new_price_target DECIMAL(10,2),
    rating_score DECIMAL(4,2),
    consensus_data JSONB, -- Full consensus response for audit
    change_type VARCHAR(50) CHECK (change_type IN ('rating', 'price_target', 'both', 'consensus')),
    data_source VARCHAR(50) DEFAULT 'fmp',
    processed_at TIMESTAMPTZ DEFAULT NOW(),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Rating update subscriptions (extends existing alert system)
CREATE TABLE IF NOT EXISTS rating_subscriptions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    symbol VARCHAR(10) NOT NULL REFERENCES stocks(symbol) ON DELETE CASCADE,
    subscription_type VARCHAR(50) NOT NULL CHECK (subscription_type IN ('rating_updates', 'price_target_updates', 'earnings_updates')),
    enabled BOOLEAN DEFAULT TRUE,
    priority INTEGER DEFAULT 2 CHECK (priority BETWEEN 1 AND 5),
    config JSONB DEFAULT '{}', -- Subscription-specific configuration
    last_processed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    
    UNIQUE(user_id, symbol, subscription_type)
);

-- Alert processing queue for efficient batch processing
CREATE TABLE IF NOT EXISTS alert_processing_queue (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    alert_id TEXT REFERENCES alerts(alert_id) ON DELETE CASCADE,
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
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Insert rating-specific alert types into existing alert_types table
INSERT INTO alert_types (alert_type_id, name, display_name, description, plugin_name, priority_level, category, is_active) VALUES
('rating_change', 'rating_change', 'Rating Change', 'Alert when analyst ratings change for monitored stocks', 'rating_plugin', 'MEDIUM', 'rating', TRUE),
('price_target_change', 'price_target_change', 'Price Target Change', 'Alert when consensus price targets change significantly', 'rating_plugin', 'MEDIUM', 'rating', TRUE),
('consensus_alert', 'consensus_alert', 'Consensus Alert', 'Alert when consensus reaches specific threshold', 'rating_plugin', 'MEDIUM', 'rating', TRUE),
('earnings_alert', 'earnings_alert', 'Earnings Alert', 'Alert for earnings announcements and surprises', 'rating_plugin', 'MEDIUM', 'earnings', TRUE)
ON CONFLICT (alert_type_id) DO NOTHING;
