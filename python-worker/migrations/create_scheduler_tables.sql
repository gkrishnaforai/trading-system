-- ============================================
-- Data Refresh Scheduler Database Setup
-- ============================================
-- Creates tables and triggers for automated data refresh scheduling
-- Compatible with PostgreSQL 12+

-- Create data_refresh_schedule table
-- This table manages automatic data refresh scheduling for all symbols
CREATE TABLE IF NOT EXISTS data_refresh_schedule (
    id SERIAL PRIMARY KEY,
    data_type VARCHAR(50) NOT NULL,
    symbol VARCHAR(10) NOT NULL,
    last_refresh TIMESTAMP,
    next_refresh TIMESTAMP,
    refresh_interval INTEGER NOT NULL,  -- minutes
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    -- Constraints
    UNIQUE(symbol, data_type),
    CONSTRAINT valid_data_type CHECK (data_type IN ('price_historical', 'indicators', 'fundamentals', 'earnings')),
    CONSTRAINT valid_interval CHECK (refresh_interval > 0 AND refresh_interval <= 1440),  -- max 24 hours
    CONSTRAINT valid_symbol CHECK (symbol ~ '^[A-Z0-9\.]{1,10}$')  -- valid stock symbols
);

-- Create indexes for performance
CREATE INDEX IF NOT EXISTS idx_refresh_schedule_next_refresh 
ON data_refresh_schedule(next_refresh, is_active) 
WHERE is_active = TRUE;

CREATE INDEX IF NOT EXISTS idx_refresh_schedule_symbol 
ON data_refresh_schedule(symbol);

CREATE INDEX IF NOT EXISTS idx_refresh_schedule_data_type 
ON data_refresh_schedule(data_type);

CREATE INDEX IF NOT EXISTS idx_refresh_schedule_active 
ON data_refresh_schedule(is_active) 
WHERE is_active = TRUE;

-- Create data_refresh_history table
-- Tracks all refresh attempts for auditing and analytics
CREATE TABLE IF NOT EXISTS data_refresh_history (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(10) NOT NULL,
    data_type VARCHAR(50) NOT NULL,
    refresh_start TIMESTAMP NOT NULL,
    refresh_end TIMESTAMP,
    status VARCHAR(20) NOT NULL,  -- 'started', 'completed', 'failed'
    records_processed INTEGER DEFAULT 0,
    error_message TEXT,
    api_calls_made INTEGER DEFAULT 0,
    duration_ms INTEGER,  -- duration in milliseconds
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    -- Constraints
    CONSTRAINT valid_status CHECK (status IN ('started', 'completed', 'failed')),
    CONSTRAINT valid_history_data_type CHECK (data_type IN ('price_historical', 'indicators', 'fundamentals', 'earnings')),
    CONSTRAINT valid_history_symbol CHECK (symbol ~ '^[A-Z0-9\.]{1,10}$')
);

-- Create indexes for history table
CREATE INDEX IF NOT EXISTS idx_refresh_history_symbol 
ON data_refresh_history(symbol);

CREATE INDEX IF NOT EXISTS idx_refresh_history_data_type 
ON data_refresh_history(data_type);

CREATE INDEX IF NOT EXISTS idx_refresh_history_status 
ON data_refresh_history(status);

CREATE INDEX IF NOT EXISTS idx_refresh_history_created_at 
ON data_refresh_history(created_at DESC);

-- Create data_refresh_stats table
-- Aggregated statistics for monitoring and reporting
CREATE TABLE IF NOT EXISTS data_refresh_stats (
    id SERIAL PRIMARY KEY,
    date DATE NOT NULL,
    data_type VARCHAR(50) NOT NULL,
    total_attempts INTEGER DEFAULT 0,
    successful_attempts INTEGER DEFAULT 0,
    failed_attempts INTEGER DEFAULT 0,
    avg_duration_ms INTEGER,
    total_records_processed INTEGER DEFAULT 0,
    total_api_calls INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    -- Constraints
    UNIQUE(date, data_type),
    CONSTRAINT valid_stats_data_type CHECK (data_type IN ('price_historical', 'indicators', 'fundamentals', 'earnings'))
);

-- Create indexes for stats table
CREATE INDEX IF NOT EXISTS idx_refresh_stats_date 
ON data_refresh_stats(date DESC);

CREATE INDEX IF NOT EXISTS idx_refresh_stats_data_type 
ON data_refresh_stats(data_type);

-- ============================================
-- Database Triggers and Functions
-- ============================================

-- Function to update updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
language 'plpgsql';

-- Trigger to auto-update updated_at for data_refresh_schedule
DROP TRIGGER IF EXISTS update_data_refresh_schedule_updated_at ON data_refresh_schedule;
CREATE TRIGGER update_data_refresh_schedule_updated_at 
    BEFORE UPDATE ON data_refresh_schedule 
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- Trigger to auto-update updated_at for data_refresh_stats
DROP TRIGGER IF EXISTS update_data_refresh_stats_updated_at ON data_refresh_stats;
CREATE TRIGGER update_data_refresh_stats_updated_at 
    BEFORE UPDATE ON data_refresh_stats 
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- Function to log refresh start
CREATE OR REPLACE FUNCTION log_refresh_start()
RETURNS TRIGGER AS
BEGIN
    INSERT INTO data_refresh_history (symbol, data_type, refresh_start, status)
    VALUES (NEW.symbol, NEW.data_type, CURRENT_TIMESTAMP, 'started');
    RETURN NEW;
END;
language 'plpgsql';

-- Function to log refresh completion
CREATE OR REPLACE FUNCTION log_refresh_completion()
RETURNS TRIGGER AS
BEGIN
    UPDATE data_refresh_history 
    SET refresh_end = CURRENT_TIMESTAMP,
        status = 'completed',
        duration_ms = EXTRACT(EPOCH FROM (CURRENT_TIMESTAMP - refresh_start)) * 1000
    WHERE symbol = NEW.symbol 
      AND data_type = NEW.data_type 
      AND refresh_end IS NULL
    ORDER BY refresh_start DESC 
    LIMIT 1;
    RETURN NEW;
END;
language 'plpgsql';

-- Function to calculate and update daily stats
CREATE OR REPLACE FUNCTION update_daily_stats()
RETURNS TRIGGER AS
BEGIN
    INSERT INTO data_refresh_stats (
        date, data_type, total_attempts, successful_attempts, 
        avg_duration_ms, total_records_processed, total_api_calls
    )
    SELECT 
        CURRENT_DATE,
        data_type,
        COUNT(*),
        COUNT(CASE WHEN status = 'completed' THEN 1 END),
        ROUND(AVG(duration_ms))::INTEGER,
        SUM(records_processed),
        SUM(api_calls_made)
    FROM data_refresh_history
    WHERE date(refresh_start) = CURRENT_DATE
      AND data_type = NEW.data_type
    GROUP BY data_type
    ON CONFLICT (date, data_type) 
    DO UPDATE SET
        total_attempts = EXCLUDED.total_attempts,
        successful_attempts = EXCLUDED.successful_attempts,
        failed_attempts = EXCLUDED.total_attempts - EXCLUDED.successful_attempts,
        avg_duration_ms = EXCLUDED.avg_duration_ms,
        total_records_processed = EXCLUDED.total_records_processed,
        total_api_calls = EXCLUDED.total_api_calls,
        updated_at = CURRENT_TIMESTAMP;
    
    RETURN NEW;
END;
language 'plpgsql';

-- Trigger to update stats when history is updated
DROP TRIGGER IF EXISTS update_refresh_stats_trigger ON data_refresh_history;
CREATE TRIGGER update_refresh_stats_trigger
    AFTER INSERT OR UPDATE ON data_refresh_history
    FOR EACH ROW EXECUTE FUNCTION update_daily_stats();

-- ============================================
-- Database Views for Monitoring
-- ============================================

-- View for active schedules with next refresh info
CREATE OR REPLACE VIEW active_refresh_schedules AS
SELECT 
    s.symbol,
    s.data_type,
    s.refresh_interval,
    s.last_refresh,
    s.next_refresh,
    CASE 
        WHEN s.next_refresh <= CURRENT_TIMESTAMP THEN 'OVERDUE'
        WHEN s.next_refresh <= CURRENT_TIMESTAMP + INTERVAL '5 minutes' THEN 'DUE_SOON'
        ELSE 'SCHEDULED'
    END as status,
    EXTRACT(EPOCH FROM (s.next_refresh - CURRENT_TIMESTAMP))/60 as minutes_until_refresh
FROM data_refresh_schedule s
WHERE s.is_active = TRUE
ORDER BY s.next_refresh ASC;

-- View for daily refresh statistics
CREATE OR REPLACE VIEW daily_refresh_performance AS
SELECT 
    date,
    data_type,
    total_attempts,
    successful_attempts,
    failed_attempts,
    ROUND((successful_attempts::FLOAT / NULLIF(total_attempts, 0)) * 100, 2) as success_rate,
    avg_duration_ms,
    total_records_processed,
    total_api_calls
FROM data_refresh_stats
ORDER BY date DESC, data_type;

-- View for symbol performance summary
CREATE OR REPLACE VIEW symbol_refresh_summary AS
SELECT 
    h.symbol,
    h.data_type,
    COUNT(*) as total_refreshes,
    COUNT(CASE WHEN h.status = 'completed' THEN 1 END) as successful_refreshes,
    ROUND(AVG(h.duration_ms)) as avg_duration_ms,
    SUM(h.records_processed) as total_records,
    MAX(h.refresh_start) as last_refresh,
    CASE 
        WHEN MAX(h.refresh_start) >= CURRENT_TIMESTAMP - INTERVAL '24 hours' THEN 'ACTIVE'
        WHEN MAX(h.refresh_start) >= CURRENT_TIMESTAMP - INTERVAL '7 days' THEN 'RECENT'
        ELSE 'STALE'
    END as activity_status
FROM data_refresh_history h
GROUP BY h.symbol, h.data_type
ORDER BY last_refresh DESC;

-- ============================================
-- Utility Functions
-- ============================================

-- Function to get overdue refreshes
CREATE OR REPLACE FUNCTION get_overdue_refreshes()
RETURNS TABLE(symbol VARCHAR, data_type VARCHAR, minutes_overdue INTEGER) AS
BEGIN
    RETURN QUERY
    SELECT 
        s.symbol,
        s.data_type,
        EXTRACT(EPOCH FROM (CURRENT_TIMESTAMP - s.next_refresh))/60 as minutes_overdue
    FROM data_refresh_schedule s
    WHERE s.is_active = TRUE 
      AND s.next_refresh <= CURRENT_TIMESTAMP
    ORDER BY minutes_overdue DESC;
END;
LANGUAGE plpgsql;

-- Function to schedule symbol refresh
CREATE OR REPLACE FUNCTION schedule_symbol_refresh(
    p_symbol VARCHAR,
    p_data_type VARCHAR,
    p_interval INTEGER DEFAULT 15
)
RETURNS BOOLEAN AS
BEGIN
    INSERT INTO data_refresh_schedule (
        symbol, data_type, refresh_interval, next_refresh, is_active
    ) VALUES (
        UPPER(p_symbol), 
        p_data_type, 
        p_interval, 
        CURRENT_TIMESTAMP + INTERVAL '1 minute',
        TRUE
    )
    ON CONFLICT (symbol, data_type) 
    DO UPDATE SET
        refresh_interval = EXCLUDED.refresh_interval,
        next_refresh = EXCLUDED.next_refresh,
        is_active = EXCLUDED.is_active,
        updated_at = CURRENT_TIMESTAMP;
    
    RETURN TRUE;
EXCEPTION WHEN OTHERS THEN
    RAISE NOTICE 'Error scheduling refresh for % %: %', p_symbol, p_data_type, SQLERRM;
    RETURN FALSE;
END;
LANGUAGE plpgsql;

-- Function to remove symbol schedule
CREATE OR REPLACE FUNCTION remove_symbol_schedule(
    p_symbol VARCHAR,
    p_data_type VARCHAR DEFAULT NULL
)
RETURNS INTEGER AS
BEGIN
    IF p_data_type IS NOT NULL THEN
        DELETE FROM data_refresh_schedule 
        WHERE symbol = UPPER(p_symbol) AND data_type = p_data_type;
        RETURN 1;
    ELSE
        DELETE FROM data_refresh_schedule 
        WHERE symbol = UPPER(p_symbol);
        RETURN (SELECT COUNT(*) FROM data_refresh_schedule WHERE symbol = UPPER(p_symbol));
    END IF;
END;
LANGUAGE plpgsql;

-- ============================================
-- Sample Data (Optional - for testing)
-- ============================================

-- Uncomment to insert sample data for testing
/*
INSERT INTO data_refresh_schedule (symbol, data_type, refresh_interval, next_refresh) VALUES
('AAPL', 'price_historical', 15, CURRENT_TIMESTAMP + INTERVAL '5 minutes'),
('AAPL', 'indicators', 30, CURRENT_TIMESTAMP + INTERVAL '10 minutes'),
('AAPL', 'fundamentals', 60, CURRENT_TIMESTAMP + INTERVAL '30 minutes'),
('GOOGL', 'price_historical', 15, CURRENT_TIMESTAMP + INTERVAL '7 minutes'),
('GOOGL', 'indicators', 30, CURRENT_TIMESTAMP + INTERVAL '15 minutes'),
('MSFT', 'price_historical', 15, CURRENT_TIMESTAMP + INTERVAL '3 minutes');
*/

-- ============================================
-- Permissions (Adjust as needed)
-- ============================================

-- Grant permissions to your application user
-- GRANT SELECT, INSERT, UPDATE, DELETE ON data_refresh_schedule TO your_app_user;
-- GRANT SELECT, INSERT, UPDATE, DELETE ON data_refresh_history TO your_app_user;
-- GRANT SELECT, INSERT, UPDATE, DELETE ON data_refresh_stats TO your_app_user;
-- GRANT SELECT ON ALL SEQUENCES IN SCHEMA public TO your_app_user;

-- Grant read-only permissions for monitoring
-- GRANT SELECT ON active_refresh_schedules TO monitoring_user;
-- GRANT SELECT ON daily_refresh_performance TO monitoring_user;
-- GRANT SELECT ON symbol_refresh_summary TO monitoring_user;

-- ============================================
-- Verification Queries
-- ============================================

-- Run these queries to verify setup:

-- Check tables were created
-- SELECT table_name FROM information_schema.tables 
-- WHERE table_schema = 'public' 
-- AND table_name LIKE 'data_refresh_%';

-- Check indexes were created
-- SELECT indexname FROM pg_indexes 
-- WHERE tablename LIKE 'data_refresh_%';

-- Check triggers were created
-- SELECT trigger_name FROM information_schema.triggers 
-- WHERE event_object_table LIKE 'data_refresh_%';

-- Check views were created
-- SELECT table_name FROM information_schema.views 
-- WHERE table_name IN ('active_refresh_schedules', 'daily_refresh_performance', 'symbol_refresh_summary');

-- Check functions were created
-- SELECT proname FROM pg_proc 
-- WHERE proname LIKE '%refresh%' OR proname LIKE '%schedule%';

-- ============================================
-- Setup Complete
-- ============================================

-- This script creates a complete data refresh scheduling system with:
-- 1. Tables for scheduling, history, and statistics
-- 2. Triggers for automatic timestamp updates and logging
-- 3. Views for monitoring and reporting
-- 4. Utility functions for common operations
-- 5. Proper indexes for performance
-- 6. Constraints for data integrity

-- After running this script, your database is ready for the scheduler service!
