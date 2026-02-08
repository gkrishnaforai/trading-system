-- ========================================
-- ENHANCED ALERT SYSTEM - Industry Standard
-- Migration: 016_enhanced_alert_system.sql
-- Supports pluggable, extensible alert system
-- ========================================

-- Grade Changes Table - Tracks detected changes
CREATE TABLE IF NOT EXISTS grade_changes (
    change_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    symbol VARCHAR(10) NOT NULL REFERENCES stocks(symbol) ON DELETE CASCADE,
    grading_company VARCHAR(100) NOT NULL,
    change_date TIMESTAMPTZ NOT NULL,
    change_type VARCHAR(20) NOT NULL CHECK (change_type IN ('upgrade', 'downgrade', 'initiate', 'suspend', 'maintain')),
    
    -- Grade information
    previous_grade VARCHAR(20),
    new_grade VARCHAR(20) NOT NULL,
    grade_difference INTEGER, -- Numerical difference (e.g., +1 for upgrade, -1 for downgrade)
    
    -- Market context
    price_at_change DECIMAL(10,2),
    price_change_percent DECIMAL(5,2), -- Price change % at time of grade
    volume_at_change BIGINT,
    volume_ratio DECIMAL(5,2), -- Volume ratio vs average
    
    -- Consensus information
    consensus_before DECIMAL(4,2), -- Consensus rating before change
    consensus_after DECIMAL(4,2), -- Consensus rating after change
    consensus_change DECIMAL(4,2), -- Consensus change
    analyst_count_before INTEGER,
    analyst_count_after INTEGER,
    
    -- Metadata
    data_source VARCHAR(50) DEFAULT 'unknown',
    source_id VARCHAR(100),
    processed_at TIMESTAMPTZ DEFAULT NOW(),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    
    -- Constraints
    UNIQUE(symbol, grading_company, change_date, data_source),
    CHECK (grade_difference IS NULL OR grade_difference != 0)
);

-- Alert Definitions - User-configured alerts
CREATE TABLE IF NOT EXISTS alert_definitions (
    alert_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    alert_name VARCHAR(200) NOT NULL,
    alert_type VARCHAR(50) NOT NULL,
    
    -- Target criteria
    symbols TEXT[], -- Array of symbols (NULL for all symbols)
    companies TEXT[], -- Array of grading companies (NULL for all)
    min_consensus_change DECIMAL(4,2), -- Minimum consensus change to trigger
    tier_1_firms_only BOOLEAN DEFAULT false,
    
    -- Filter conditions
    include_upgrades BOOLEAN DEFAULT true,
    include_downgrades BOOLEAN DEFAULT true,
    include_initiations BOOLEAN DEFAULT true,
    include_suspensions BOOLEAN DEFAULT false,
    include_maintains BOOLEAN DEFAULT false,
    
    -- Advanced filters
    min_price_change_percent DECIMAL(5,2), -- Minimum price change %
    max_price_change_percent DECIMAL(5,2), -- Maximum price change %
    min_volume_ratio DECIMAL(5,2), -- Minimum volume ratio
    grade_tiers TEXT[], -- Specific grade tiers to monitor
    
    -- Configuration
    notification_channels TEXT[] DEFAULT ARRAY['email'],
    notification_config JSONB DEFAULT '{}', -- Channel-specific config
    cooldown_minutes INTEGER DEFAULT 60, -- Minimum minutes between similar alerts
    
    -- Status
    is_active BOOLEAN DEFAULT true,
    last_triggered_at TIMESTAMPTZ,
    trigger_count INTEGER DEFAULT 0,
    
    -- Metadata
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    
    -- Constraints
    CHECK (array_length(symbols, 1) > 0 OR array_length(companies, 1) > 0),
    CHECK (cooldown_minutes >= 0 AND cooldown_minutes <= 1440) -- Max 24 hours
);

-- Alert Events - Triggered alert instances
CREATE TABLE IF NOT EXISTS alert_events (
    event_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    alert_id UUID NOT NULL REFERENCES alert_definitions(alert_id) ON DELETE CASCADE,
    change_id UUID NOT NULL REFERENCES grade_changes(change_id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    
    -- Event details
    trigger_reason TEXT NOT NULL, -- Why this alert was triggered
    trigger_score DECIMAL(5,2), -- How well this matches the alert criteria
    urgency_level VARCHAR(20) DEFAULT 'medium' CHECK (urgency_level IN ('low', 'medium', 'high', 'critical')),
    
    -- Status tracking
    status VARCHAR(20) DEFAULT 'pending' CHECK (status IN ('pending', 'processing', 'sent', 'failed', 'cancelled')),
    processed_at TIMESTAMPTZ,
    sent_at TIMESTAMPTZ,
    error_message TEXT,
    
    -- Metadata
    created_at TIMESTAMPTZ DEFAULT NOW(),
    
    -- Constraints
    UNIQUE(alert_id, change_id) -- Prevent duplicate alerts for same change
);

-- Notification Queue - Pending notifications
CREATE TABLE IF NOT EXISTS notification_queue (
    queue_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    event_id UUID NOT NULL REFERENCES alert_events(event_id) ON DELETE CASCADE,
    channel_type VARCHAR(20) NOT NULL CHECK (channel_type IN ('email', 'sms', 'push', 'webhook')),
    recipient VARCHAR(500) NOT NULL, -- Email, phone number, device token, or webhook URL
    
    -- Message content
    subject VARCHAR(500),
    message_body TEXT NOT NULL,
    template_data JSONB DEFAULT '{}',
    
    -- Delivery tracking
    status VARCHAR(20) DEFAULT 'pending' CHECK (status IN ('pending', 'processing', 'sent', 'failed', 'cancelled')),
    attempts INTEGER DEFAULT 0,
    max_attempts INTEGER DEFAULT 3,
    last_attempt_at TIMESTAMPTZ,
    next_attempt_at TIMESTAMPTZ DEFAULT NOW(),
    sent_at TIMESTAMPTZ,
    error_message TEXT,
    
    -- Metadata
    created_at TIMESTAMPTZ DEFAULT NOW(),
    
    -- Constraints
    CHECK (attempts >= 0 AND attempts <= max_attempts)
);

-- Scheduled Jobs - Job management
CREATE TABLE IF NOT EXISTS scheduled_jobs (
    job_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    job_name VARCHAR(100) NOT NULL UNIQUE,
    job_type VARCHAR(50) NOT NULL,
    
    -- Schedule configuration
    cron_expression VARCHAR(100), -- Cron expression for complex schedules
    interval_minutes INTEGER, -- Simple interval in minutes
    timezone VARCHAR(50) DEFAULT 'UTC',
    
    -- Job configuration
    job_config JSONB DEFAULT '{}',
    is_active BOOLEAN DEFAULT true,
    
    -- Execution tracking
    last_run_at TIMESTAMPTZ,
    next_run_at TIMESTAMPTZ,
    run_count INTEGER DEFAULT 0,
    success_count INTEGER DEFAULT 0,
    failure_count INTEGER DEFAULT 0,
    last_duration_ms INTEGER,
    last_error TEXT,
    
    -- Metadata
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    
    -- Constraints
    CHECK (cron_expression IS NOT NULL OR interval_minutes IS NOT NULL),
    CHECK (interval_minutes IS NULL OR interval_minutes > 0)
);

-- Job Execution Log - Detailed job history
CREATE TABLE IF NOT EXISTS job_execution_log (
    log_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    job_id UUID NOT NULL REFERENCES scheduled_jobs(job_id) ON DELETE CASCADE,
    
    -- Execution details
    started_at TIMESTAMPTZ NOT NULL,
    completed_at TIMESTAMPTZ,
    duration_ms INTEGER,
    status VARCHAR(20) NOT NULL CHECK (status IN ('running', 'completed', 'failed', 'cancelled')),
    
    -- Results
    records_processed INTEGER DEFAULT 0,
    records_failed INTEGER DEFAULT 0,
    alerts_generated INTEGER DEFAULT 0,
    
    -- Error details
    error_message TEXT,
    error_stack TEXT,
    
    -- Metadata
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_grade_changes_symbol_date ON grade_changes(symbol, change_date DESC);
CREATE INDEX IF NOT EXISTS idx_grade_changes_company_date ON grade_changes(grading_company, change_date DESC);
CREATE INDEX IF NOT EXISTS idx_grade_changes_processed ON grade_changes(processed_at) WHERE processed_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_grade_changes_consensus ON grade_changes(consensus_change) WHERE consensus_change IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_alert_definitions_user_active ON alert_definitions(user_id, is_active) WHERE is_active = true;
CREATE INDEX IF NOT EXISTS idx_alert_definitions_type ON alert_definitions(alert_type);
CREATE INDEX IF NOT EXISTS idx_alert_definitions_symbols ON alert_definitions USING GIN(symbols);
CREATE INDEX IF NOT EXISTS idx_alert_definitions_companies ON alert_definitions USING GIN(companies);

CREATE INDEX IF NOT EXISTS idx_alert_events_status ON alert_events(status);
CREATE INDEX IF NOT EXISTS idx_alert_events_created ON alert_events(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_alert_events_user_created ON alert_events(user_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_notification_queue_status ON notification_queue(status);
CREATE INDEX IF NOT EXISTS idx_notification_queue_next_attempt ON notification_queue(next_attempt_at) WHERE status IN ('pending', 'failed');
CREATE INDEX IF NOT EXISTS idx_notification_queue_channel ON notification_queue(channel_type);

CREATE INDEX IF NOT EXISTS idx_scheduled_jobs_next_run ON scheduled_jobs(next_run_at) WHERE is_active = true;
CREATE INDEX IF NOT EXISTS idx_job_execution_log_job_started ON job_execution_log(job_id, started_at DESC);

-- Insert default scheduled jobs
INSERT INTO scheduled_jobs (job_name, job_type, interval_minutes, job_config) VALUES
('grade_collection', 'data_collection', 15, '{"sources": ["fmp", "alpha_vantage"], "batch_size": 100}'),
('change_detection', 'change_detection', 5, '{"lookback_minutes": 30, "batch_size": 50}'),
('alert_evaluation', 'alert_evaluation', 2, '{"batch_size": 100, "parallel_workers": 4}'),
('notification_delivery', 'notification_delivery', 1, '{"batch_size": 50, "retry_delay_minutes": 5}'),
('cleanup_old_data', 'maintenance', 1440, '{"retention_days": 90, "batch_size": 1000}')
ON CONFLICT (job_name) DO NOTHING;

-- Create trigger for updating updated_at
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

CREATE TRIGGER update_alert_definitions_updated_at BEFORE UPDATE ON alert_definitions FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
CREATE TRIGGER update_scheduled_jobs_updated_at BEFORE UPDATE ON scheduled_jobs FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
