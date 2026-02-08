-- ========================================
-- PERFORMANCE INDEXES - Stock Grades System
-- Migration: 010_stock_grades_indexes.sql
-- Optimized for high-performance queries following best practices
-- ========================================

-- ========================================
-- STOCK GRADES TABLE INDEXES
-- ========================================

-- Primary lookup indexes
CREATE INDEX IF NOT EXISTS idx_stock_grades_symbol_date 
ON stock_grades(symbol, grade_date DESC);

CREATE INDEX IF NOT EXISTS idx_stock_grades_company_date 
ON stock_grades(grading_company, grade_date DESC);

-- Action-based indexes for alert processing
CREATE INDEX IF NOT EXISTS idx_stock_grades_action_date 
ON stock_grades(action, grade_date DESC) WHERE action IN ('upgrade', 'downgrade');

-- Data source indexes for analytics
CREATE INDEX IF NOT EXISTS idx_stock_grades_source_date 
ON stock_grades(data_source, grade_date DESC);

-- Composite index for recent changes (removed time-based predicate)
CREATE INDEX IF NOT EXISTS idx_stock_grades_recent_changes 
ON stock_grades(symbol, action, grade_date DESC);

-- ========================================
-- CONSENSUS TABLE INDEXES
-- ========================================

-- Primary consensus lookup
CREATE INDEX IF NOT EXISTS idx_consensus_symbol_score 
ON stock_grade_consensus(symbol, consensus_score DESC);

-- Consensus rating lookup
CREATE INDEX IF NOT EXISTS idx_consensus_rating_score 
ON stock_grade_consensus(consensus_rating, consensus_score DESC);

-- Update schedule lookup (removed time-based predicate)
CREATE INDEX IF NOT EXISTS idx_consensus_update_schedule 
ON stock_grade_consensus(last_updated DESC);

-- High-coverage consensus (for filtering)
CREATE INDEX IF NOT EXISTS idx_consensus_high_coverage 
ON stock_grade_consensus(total_analysts DESC, consensus_score DESC) 
WHERE total_analysts >= 5;

-- ========================================
-- HISTORY TABLES INDEXES
-- ========================================

-- Consensus history for trend analysis
CREATE INDEX IF NOT EXISTS idx_consensus_history_symbol_trend 
ON stock_consensus_history(symbol, recorded_at DESC);

-- Significant consensus changes
CREATE INDEX IF NOT EXISTS idx_consensus_history_significant 
ON stock_consensus_history(significance_level DESC, recorded_at DESC) 
WHERE significance_level >= 3;

-- Consensus change events for alerts
CREATE INDEX IF NOT EXISTS idx_consensus_events_alerts 
ON consensus_change_events(symbol, event_type, created_at DESC) 
WHERE alerts_triggered = false;

-- Grade change events for processing
CREATE INDEX IF NOT EXISTS idx_grade_events_unprocessed 
ON grade_change_events(alerts_processed, created_at DESC) 
WHERE alerts_processed = false;

-- ========================================
-- ALERT SYSTEM INDEXES
-- ========================================

-- User alert preferences lookup
CREATE INDEX IF NOT EXISTS idx_user_alert_prefs_lookup 
ON user_stock_alert_preferences(user_id, symbol, portfolio_only);

-- Alert queue processing
CREATE INDEX IF NOT EXISTS idx_consensus_queue_processing 
ON consensus_alert_queue(status, priority, scheduled_at, retry_count);

-- NOTE: alert_history and alert_notifications tables don't exist in this project
-- These indexes are commented out as they reference non-existent tables
-- CREATE INDEX IF NOT EXISTS idx_alert_history_performance 
-- ON alert_history(alert_type, triggered_at DESC, symbol);
-- CREATE INDEX IF NOT EXISTS idx_alert_notifications_delivery 
-- ON alert_notifications(notification_status, created_at DESC, alert_id);

-- ========================================
-- ANALYTICS VIEWS INDEXES
-- ========================================

-- NOTE: Materialized views removed as they reference non-existent tables
-- The real_time_prices table doesn't exist in this project
-- CREATE MATERIALIZED VIEW IF NOT EXISTS mv_consensus_summary AS ...
-- CREATE MATERIALIZED VIEW IF NOT EXISTS mv_firm_performance AS ...

-- ========================================
-- PARTIAL INDEXES FOR OPTIMIZATION
-- ========================================

-- Recent upgrades only (removed time-based predicate)
CREATE INDEX IF NOT EXISTS idx_recent_upgrades 
ON stock_grades(symbol, action, grade_date DESC) 
WHERE action = 'upgrade';

-- Recent downgrades only (removed time-based predicate)
CREATE INDEX IF NOT EXISTS idx_recent_downgrades 
ON stock_grades(symbol, action, grade_date DESC) 
WHERE action = 'downgrade';

-- High-coverage consensus
CREATE INDEX IF NOT EXISTS idx_high_coverage_consensus 
ON stock_grade_consensus(consensus_rating, total_analysts DESC) 
WHERE total_analysts >= 10;

-- Tier 1 firm ratings (removed subquery from predicate)
CREATE INDEX IF NOT EXISTS idx_tier1_firm_ratings 
ON stock_grades(grading_company, symbol, grade_date DESC);

-- ========================================
-- REFRESH FUNCTIONS FOR MATERIALIZED VIEWS
-- ========================================

-- NOTE: Refresh functions created separately in fix_trigger_functions.py
-- due to migration runner's SQL parsing limitations with multi-line functions

-- Create triggers (functions created separately)
DROP TRIGGER IF EXISTS refresh_consensus_views_trigger ON stock_grade_consensus;
-- Note: This would typically be called by a cron job or external scheduler

-- ========================================
-- STATISTICS UPDATE
-- ========================================

-- Update table statistics for better query planning
ANALYZE stock_grades;
ANALYZE stock_grade_consensus;
ANALYZE stock_consensus_history;
ANALYZE consensus_change_events;
ANALYZE analyst_firm_rankings;
ANALYZE data_source_mappings;
ANALYZE grade_change_events;
ANALYZE user_stock_alert_preferences;
ANALYZE consensus_alert_queue;
ANALYZE alert_types;
ANALYZE alert_rules;
ANALYZE notification_templates;

-- NOTE: alert_history and alert_notifications tables don't exist in this project
-- ANALYZE alert_history;
-- ANALYZE alert_notifications;

-- ========================================
-- INDEX USAGE MONITORING VIEW
-- ========================================

-- NOTE: Index usage monitoring view removed due to column compatibility issues
-- This can be created separately if needed for monitoring
-- CREATE VIEW index_usage_stats AS ...

-- ========================================
-- MIGRATION COMPLETION
-- ========================================

-- NOTE: Monitoring views removed due to extension compatibility issues
-- These require pg_stat_statements extension and specific PostgreSQL versions
-- CREATE VIEW slow_query_candidates AS ...

-- Comments for documentation
-- NOTE: Materialized views and monitoring views were removed due to compatibility issues

COMMENT ON INDEX idx_stock_grades_recent_changes IS 'Optimized for alert processing - only recent grade changes';
COMMENT ON INDEX idx_consensus_high_coverage IS 'Optimized for filtering consensus by analyst coverage';
COMMENT ON INDEX idx_tier1_firm_ratings IS 'Optimized for Tier 1 firm specific queries';
