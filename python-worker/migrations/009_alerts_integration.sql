-- ========================================
-- ALERTS INTEGRATION - Stock Grades & Consensus
-- Migration: 009_alerts_integration.sql
-- Integrates with existing alert system following SOLID principles
-- ========================================

-- Create alert_types table if it doesn't exist
CREATE TABLE IF NOT EXISTS alert_types (
    alert_type_id VARCHAR(50) PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    display_name VARCHAR(100) NOT NULL,
    description TEXT,
    plugin_name VARCHAR(50),
    priority_level VARCHAR(20) CHECK (priority_level IN ('LOW', 'MEDIUM', 'HIGH', 'CRITICAL')),
    category VARCHAR(50),
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Create alert_rules table if it doesn't exist
DROP TABLE IF EXISTS alert_rules CASCADE;
CREATE TABLE alert_rules (
    rule_name VARCHAR(100) PRIMARY KEY,
    rule_type VARCHAR(50) NOT NULL CHECK (rule_type IN ('stock_grade_upgrade', 'stock_grade_downgrade', 'stock_grade_initiate', 'stock_grade_suspend', 'consensus_upgrade', 'consensus_downgrade', 'consensus_initiate', 'consensus_suspend', 'custom')),
    conditions JSONB,
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Create notification_templates table if it doesn't exist
CREATE TABLE IF NOT EXISTS notification_templates (
    template_name VARCHAR(100) PRIMARY KEY,
    template_type VARCHAR(20) CHECK (template_type IN ('email', 'sms', 'push', 'webhook')),
    subject_template TEXT,
    body_template TEXT,
    variables JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Extend alert_types with stock grade specific types
INSERT INTO alert_types (alert_type_id, name, display_name, description, plugin_name, priority_level, category) VALUES
('stock_grade_upgrade', 'Stock Grade Upgrade', '📈 Analyst Upgrade', 'Individual analyst upgrades stock rating', 'stock_grade_plugin', 'MEDIUM', 'analyst_ratings'),
('stock_grade_downgrade', 'Stock Grade Downgrade', '📉 Analyst Downgrade', 'Individual analyst downgrades stock rating', 'stock_grade_plugin', 'MEDIUM', 'analyst_ratings'),
('stock_grade_initiate', 'Stock Grade Initiation', '🆕 New Coverage', 'Analyst initiates coverage on stock', 'stock_grade_plugin', 'LOW', 'analyst_ratings'),
('stock_grade_suspend', 'Stock Grade Suspension', '🔕 Coverage Suspended', 'Analyst suspends coverage on stock', 'stock_grade_plugin', 'LOW', 'analyst_ratings'),
('consensus_upgrade', 'Consensus Upgrade', '🚀 Market Consensus Upgrade', 'Overall analyst consensus upgraded - HIGH PRIORITY', 'consensus_plugin', 'HIGH', 'market_sentiment'),
('consensus_downgrade', 'Consensus Downgrade', '⚠️ Market Consensus Downgrade', 'Overall analyst consensus downgraded - HIGH PRIORITY', 'consensus_plugin', 'HIGH', 'market_sentiment'),
('consensus_initiate', 'Consensus Initiated', '📊 New Coverage Consensus', 'New analyst consensus established for stock', 'consensus_plugin', 'MEDIUM', 'market_sentiment'),
('consensus_suspend', 'Consensus Suspended', '🔕 Coverage Suspended', 'Analyst consensus suspended - no coverage', 'consensus_plugin', 'MEDIUM', 'market_sentiment')
ON CONFLICT (alert_type_id) DO NOTHING;

-- Alert rules templates for stock grades
INSERT INTO alert_rules (rule_name, rule_type, conditions, is_active) VALUES
('Tier 1 Firm Upgrades', 'stock_grade_upgrade', '{"min_firm_tier": "Tier 1", "grade_types": ["upgrade"], "exclude_maintains": true}', true),
('Significant Consensus Changes', 'consensus_upgrade', '{"min_significance_level": 3, "min_analyst_count": 5}', true),
('High-Impact Consensus Downgrades', 'consensus_downgrade', '{"min_significance_level": 4, "min_analyst_count": 3}', true),
('All Individual Downgrades', 'stock_grade_downgrade', '{"grade_types": ["downgrade"], "all_firms": true}', true)
ON CONFLICT (rule_name) DO NOTHING;

-- Notification templates for stock grade alerts
INSERT INTO notification_templates (template_name, template_type, subject_template, body_template, variables) VALUES
('stock_grade_upgrade_email', 'email', '📈 {symbol} upgraded by {grading_company} from {previous_grade} to {new_grade}', 
 'Analyst {grading_company} has upgraded {symbol} from {previous_grade} to {new_grade}.\n\nGrade Date: {grade_date}\nPrice at Grade: ${price_at_grade}\n\nView detailed analysis: {analysis_link}', 
 '["symbol", "grading_company", "previous_grade", "new_grade", "grade_date", "price_at_grade", "analysis_link"]'),

('stock_grade_downgrade_email', 'email', '📉 {symbol} downgraded by {grading_company} from {previous_grade} to {new_grade}', 
 'Analyst {grading_company} has downgraded {symbol} from {previous_grade} to {new_grade}.\n\nGrade Date: {grade_date}\nPrice at Grade: ${price_at_grade}\n\nReview your position: {analysis_link}', 
 '["symbol", "grading_company", "previous_grade", "new_grade", "grade_date", "price_at_grade", "analysis_link"]'),

('consensus_upgrade_email', 'email', '🚀 MARKET CONSENSUS UPGRADE: {symbol} upgraded to {new_consensus}', 
 '🚀 **MARKET CONSENSUS UPGRADE** 🚀\n\n**{symbol}** has been upgraded by the overall analyst consensus!\n\n**Rating Change:** {previous_consensus} → {new_consensus}\n**Analyst Coverage:** {analyst_count} firms\n**Consensus Score:** {consensus_score}/2.0\n**Significance:** {significance_description}\n\n**Current Distribution:**\n• Strong Buy: {strong_buy} analysts\n• Buy: {buy} analysts\n• Hold: {hold} analysts\n• Sell: {sell} analysts\n• Strong Sell: {strong_sell} analysts\n\n**What This Means:**\nThis represents a significant shift in market sentiment as multiple analysts have collectively upgraded their ratings for {symbol}. This consensus upgrade often precedes positive price momentum.\n\nView detailed analysis: {analysis_link}', 
 '["symbol", "new_consensus", "previous_consensus", "analyst_count", "consensus_score", "significance_description", "strong_buy", "buy", "hold", "sell", "strong_sell", "analysis_link"]'),

('consensus_downgrade_email', 'email', '⚠️ MARKET CONSENSUS DOWNGRADE: {symbol} downgraded to {new_consensus}', 
 '⚠️ **MARKET CONSENSUS DOWNGRADE** ⚠️\n\n**{symbol}** has been downgraded by the overall analyst consensus!\n\n**Rating Change:** {previous_consensus} → {new_consensus}\n**Analyst Coverage:** {analyst_count} firms\n**Consensus Score:** {consensus_score}/2.0\n**Significance:** {significance_description}\n\n**Current Distribution:**\n• Strong Buy: {strong_buy} analysts\n• Buy: {buy} analysts\n• Hold: {hold} analysts\n• Sell: {sell} analysts\n• Strong Sell: {strong_sell} analysts\n\n**Risk Warning:**\nThis represents a significant shift in market sentiment. Consider reviewing your position in {symbol}.\n\nReview your position: {analysis_link}', 
 '["symbol", "new_consensus", "previous_consensus", "analyst_count", "consensus_score", "significance_description", "strong_buy", "buy", "hold", "sell", "strong_sell", "analysis_link"]'),

('stock_grade_sms', 'sms', '{symbol}: {grading_company} {action} from {previous_grade} to {new_grade}', 
 '{symbol}: {grading_company} {action} from {previous_grade} to {new_grade}. Price: ${price_at_grade}', 
 '["symbol", "grading_company", "action", "previous_grade", "new_grade", "price_at_grade"]'),

('consensus_sms', 'sms', '🚀 {symbol} CONSENSUS {change_type}: {previous_consensus} → {new_consensus}', 
 '🚀 {symbol} consensus {change_type}: {previous_consensus} → {new_consensus}. {analyst_count} analysts. Score: {consensus_score}', 
 '["symbol", "change_type", "previous_consensus", "new_consensus", "analyst_count", "consensus_score"]')
ON CONFLICT (template_name) DO NOTHING;

-- User alert preferences for stock grades (extends existing system)
CREATE TABLE IF NOT EXISTS user_stock_alert_preferences (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    symbol VARCHAR(10) REFERENCES stocks(symbol) ON DELETE CASCADE,
    
    -- Alert preferences
    stock_grade_alerts_enabled BOOLEAN DEFAULT true,
    consensus_alerts_enabled BOOLEAN DEFAULT true,
    portfolio_only BOOLEAN DEFAULT true,
    
    -- Notification channels
    email_enabled BOOLEAN DEFAULT true,
    sms_enabled BOOLEAN DEFAULT false,
    push_enabled BOOLEAN DEFAULT false,
    
    -- Filtering preferences
    min_firm_tier VARCHAR(20) DEFAULT 'Tier 2' CHECK (min_firm_tier IN ('Tier 1', 'Tier 2', 'Tier 3', 'Tier 4', 'All')),
    min_significance_level INTEGER DEFAULT 3 CHECK (min_significance_level BETWEEN 1 AND 5),
    
    -- Metadata
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    
    UNIQUE(user_id, symbol)
);

-- Alert processing queue for high-priority consensus changes
CREATE TABLE IF NOT EXISTS consensus_alert_queue (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    consensus_event_id UUID NOT NULL REFERENCES consensus_change_events(id) ON DELETE CASCADE,
    
    -- Processing status
    status VARCHAR(20) DEFAULT 'pending' CHECK (status IN ('pending', 'processing', 'completed', 'failed')),
    priority INTEGER DEFAULT 5 CHECK (priority BETWEEN 1 AND 10),  -- 1=highest priority
    severity VARCHAR(20) DEFAULT 'INFO' CHECK (severity IN ('INFO', 'WARNING', 'CRITICAL')),
    
    -- Alert details
    alert_type_id VARCHAR(50) NOT NULL,
    symbol VARCHAR(10) NOT NULL,
    consensus_change VARCHAR(20) NOT NULL,
    previous_consensus VARCHAR(20),
    new_consensus VARCHAR(20),
    significance_level INTEGER,
    market_impact VARCHAR(20),
    total_analysts INTEGER,
    consensus_score_change DECIMAL(3,1),
    
    -- Scheduling
    scheduled_at TIMESTAMPTZ DEFAULT NOW(),
    processed_at TIMESTAMPTZ,
    retry_count INTEGER DEFAULT 0,
    max_retries INTEGER DEFAULT 3,
    
    -- Error handling
    error_message TEXT,
    last_error_at TIMESTAMPTZ,
    
    -- Metadata
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- NOTE: Views for analytics would require additional alert system tables
-- These are commented out as they depend on tables not in this project
-- CREATE VIEW stock_grade_alert_stats AS ...
-- CREATE VIEW consensus_impact_analysis AS ...

-- NOTE: Trigger functions and triggers created separately in fix_trigger_functions.py
-- due to migration runner's SQL parsing limitations with multi-line functions
-- Run fix_trigger_functions.py first, then migrations

-- Comments for documentation
COMMENT ON TABLE user_stock_alert_preferences IS 'User-specific preferences for stock grade and consensus alerts';
COMMENT ON TABLE consensus_alert_queue IS 'High-priority queue for processing consensus change alerts';

COMMENT ON COLUMN user_stock_alert_preferences.min_firm_tier IS 'Minimum analyst firm tier to trigger alerts (Tier 1, Tier 2, Tier 3, Tier 4, All)';
COMMENT ON COLUMN user_stock_alert_preferences.min_significance_level IS 'Minimum significance level (1-5) to trigger consensus alerts';
COMMENT ON COLUMN consensus_alert_queue.priority IS 'Priority level: 1=highest, 10=lowest';
