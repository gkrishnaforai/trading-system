-- Fix trigger functions for stock grades system
-- Execute this directly in PostgreSQL: psql -d your_database -f fix_trigger_functions.sql

-- Create function to update updated_at
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
language 'plpgsql';

-- Create trigger for grade change events
CREATE OR REPLACE FUNCTION trigger_grade_change_event()
RETURNS TRIGGER AS
BEGIN
    INSERT INTO grade_change_events (
        stock_grade_id,
        symbol,
        event_type,
        grading_company,
        previous_grade,
        new_grade,
        grade_date,
        price_at_grade,
        volume_at_grade,
        market_cap_at_grade
    )
    VALUES (
        NEW.id,
        NEW.symbol,
        NEW.action,
        NEW.grading_company,
        NEW.previous_grade,
        NEW.new_grade,
        NEW.grade_date::date,
        NEW.price_at_grade,
        NEW.volume_at_grade,
        NEW.market_cap_at_grade
    );

    RETURN NEW;
END;
language 'plpgsql';

-- Create trigger for consensus change events
CREATE OR REPLACE FUNCTION trigger_consensus_change_event()
RETURNS TRIGGER AS
BEGIN
    -- Only trigger if consensus rating actually changed
    IF OLD.consensus_rating IS DISTINCT FROM NEW.consensus_rating THEN
        -- Insert into consensus_change_events
        INSERT INTO consensus_change_events (
            symbol, previous_consensus, new_consensus, consensus_change,
            consensus_score, previous_score, consensus_score_change,
            total_analysts, previous_analysts, analyst_count_change,
            significance_level, market_impact
        ) VALUES (
            NEW.symbol, OLD.consensus_rating, NEW.consensus_rating,
            CASE 
                WHEN OLD.consensus_rating IS NULL THEN 'initiate'
                WHEN NEW.consensus_rating > OLD.consensus_rating THEN 'upgrade'
                WHEN NEW.consensus_rating < OLD.consensus_rating THEN 'downgrade'
                ELSE 'maintain'
            END,
            NEW.consensus_score, OLD.consensus_score,
            COALESCE(NEW.consensus_score, 0) - COALESCE(OLD.consensus_score, 0),
            NEW.total_analysts, OLD.total_analysts,
            COALESCE(NEW.total_analysts, 0) - COALESCE(OLD.total_analysts, 0),
            -- Calculate significance level (1-5)
            CASE 
                WHEN ABS(COALESCE(NEW.consensus_score, 0) - COALESCE(OLD.consensus_score, 0)) >= 1.0 THEN 5
                WHEN ABS(COALESCE(NEW.consensus_score, 0) - COALESCE(OLD.consensus_score, 0)) >= 0.7 THEN 4
                WHEN ABS(COALESCE(NEW.consensus_score, 0) - COALESCE(OLD.consensus_score, 0)) >= 0.5 THEN 3
                WHEN ABS(COALESCE(NEW.consensus_score, 0) - COALESCE(OLD.consensus_score, 0)) >= 0.3 THEN 2
                ELSE 1
            END,
            -- Assess market impact
            CASE 
                WHEN ABS(COALESCE(NEW.consensus_score, 0) - COALESCE(OLD.consensus_score, 0)) >= 1.0 
                 AND COALESCE(NEW.total_analysts, 0) >= 10 THEN 'VERY_HIGH'
                WHEN ABS(COALESCE(NEW.consensus_score, 0) - COALESCE(OLD.consensus_score, 0)) >= 0.7 
                 AND COALESCE(NEW.total_analysts, 0) >= 5 THEN 'HIGH'
                WHEN ABS(COALESCE(NEW.consensus_score, 0) - COALESCE(OLD.consensus_score, 0)) >= 0.5 
                 AND COALESCE(NEW.total_analysts, 0) >= 3 THEN 'MEDIUM'
                ELSE 'LOW'
            END
        );
        
        -- Insert into consensus history (for tracking)
        INSERT INTO stock_consensus_history (
            symbol, strong_buy, buy, hold, sell, strong_sell, consensus_rating,
            consensus_score, total_analysts, previous_consensus, consensus_change,
            consensus_score_change, significance_level, market_impact, data_source
        ) VALUES (
            NEW.symbol, NEW.strong_buy, NEW.buy, NEW.hold, NEW.sell, NEW.strong_sell,
            NEW.consensus_rating, NEW.consensus_score, NEW.total_analysts,
            OLD.consensus_rating,
            CASE 
                WHEN OLD.consensus_rating IS NULL THEN 'initiate'
                WHEN NEW.consensus_rating > OLD.consensus_rating THEN 'upgrade'
                WHEN NEW.consensus_rating < OLD.consensus_rating THEN 'downgrade'
                ELSE 'maintain'
            END,
            COALESCE(NEW.consensus_score, 0) - COALESCE(OLD.consensus_score, 0),
            CASE 
                WHEN ABS(COALESCE(NEW.consensus_score, 0) - COALESCE(OLD.consensus_score, 0)) >= 1.0 THEN 5
                WHEN ABS(COALESCE(NEW.consensus_score, 0) - COALESCE(OLD.consensus_score, 0)) >= 0.7 THEN 4
                WHEN ABS(COALESCE(NEW.consensus_score, 0) - COALESCE(OLD.consensus_score, 0)) >= 0.5 THEN 3
                WHEN ABS(COALESCE(NEW.consensus_score, 0) - COALESCE(OLD.consensus_score, 0)) >= 0.3 THEN 2
                ELSE 1
            END,
            CASE 
                WHEN ABS(COALESCE(NEW.consensus_score, 0) - COALESCE(OLD.consensus_score, 0)) >= 1.0 
                 AND COALESCE(NEW.total_analysts, 0) >= 10 THEN 'VERY_HIGH'
                WHEN ABS(COALESCE(NEW.consensus_score, 0) - COALESCE(OLD.consensus_score, 0)) >= 0.7 
                 AND COALESCE(NEW.total_analysts, 0) >= 5 THEN 'HIGH'
                WHEN ABS(COALESCE(NEW.consensus_score, 0) - COALESCE(OLD.consensus_score, 0)) >= 0.5 
                 AND COALESCE(NEW.total_analysts, 0) >= 3 THEN 'MEDIUM'
                ELSE 'LOW'
            END,
            NEW.data_source
        );
        
        -- Notify consensus change listeners
        NOTIFY consensus_change, NEW.symbol || '|' || 
            CASE 
                WHEN OLD.consensus_rating IS NULL THEN 'initiate'
                WHEN NEW.consensus_rating > OLD.consensus_rating THEN 'upgrade'
                WHEN NEW.consensus_rating < OLD.consensus_rating THEN 'downgrade'
                ELSE 'maintain'
            END;
    END IF;
    
    RETURN NEW;
END;
language 'plpgsql';

-- Create triggers if they don't exist
DROP TRIGGER IF EXISTS trigger_grade_change_event ON stock_grades;
CREATE TRIGGER trigger_grade_change_event
AFTER INSERT ON stock_grades
FOR EACH ROW EXECUTE FUNCTION trigger_grade_change_event();

DROP TRIGGER IF EXISTS update_stock_grades_updated_at ON stock_grades;
CREATE TRIGGER update_stock_grades_updated_at 
BEFORE UPDATE ON stock_grades 
FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

DROP TRIGGER IF EXISTS update_analyst_firm_rankings_updated_at ON analyst_firm_rankings;
CREATE TRIGGER update_analyst_firm_rankings_updated_at 
BEFORE UPDATE ON analyst_firm_rankings 
FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

DROP TRIGGER IF EXISTS trigger_consensus_change_event ON stock_grade_consensus;
CREATE TRIGGER trigger_consensus_change_event
AFTER UPDATE ON stock_grade_consensus
FOR EACH ROW EXECUTE FUNCTION trigger_consensus_change_event();

DROP TRIGGER IF EXISTS update_consensus_updated_at ON stock_grade_consensus;
CREATE TRIGGER update_consensus_updated_at 
BEFORE UPDATE ON stock_grade_consensus 
FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

DROP TRIGGER IF EXISTS update_consensus_schedule_updated_at ON consensus_update_schedule;
CREATE TRIGGER update_consensus_schedule_updated_at 
BEFORE UPDATE ON consensus_update_schedule 
FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- Create trigger for alert queue processing
CREATE OR REPLACE FUNCTION queue_consensus_alert()
RETURNS TRIGGER AS
BEGIN
    -- Only queue significant consensus changes
    IF NEW.significance_level >= 3 THEN
        INSERT INTO consensus_alert_queue (
            symbol, consensus_change, previous_consensus, new_consensus,
            significance_level, market_impact, total_analysts, consensus_score_change,
            alert_type_id, priority, severity, status, scheduled_at
        ) VALUES (
            NEW.symbol, NEW.consensus_change, NEW.previous_consensus, NEW.new_consensus,
            NEW.significance_level, NEW.market_impact, NEW.total_analysts, NEW.consensus_score_change,
            'consensus_change',
            CASE 
                WHEN NEW.significance_level >= 4 AND NEW.market_impact IN ('HIGH', 'VERY_HIGH') THEN 'HIGH'
                WHEN NEW.significance_level >= 3 THEN 'MEDIUM'
                ELSE 'LOW'
            END,
            CASE 
                WHEN NEW.significance_level >= 4 AND NEW.market_impact IN ('HIGH', 'VERY_HIGH') THEN 'CRITICAL'
                WHEN NEW.significance_level >= 3 THEN 'WARNING'
                ELSE 'INFO'
            END,
            'QUEUED',
            NOW()
        );
        
        -- Notify alert processor
        NOTIFY consensus_alert, NEW.symbol || '|' || NEW.consensus_change;
    END IF;
    
    RETURN NEW;
END;
language 'plpgsql';

DROP TRIGGER IF EXISTS queue_consensus_alert ON consensus_change_events;
CREATE TRIGGER queue_consensus_alert
AFTER INSERT ON consensus_change_events
FOR EACH ROW EXECUTE FUNCTION queue_consensus_alert();

DROP TRIGGER IF EXISTS update_user_stock_alert_preferences_updated_at ON user_stock_alert_preferences;
CREATE TRIGGER update_user_stock_alert_preferences_updated_at 
BEFORE UPDATE ON user_stock_alert_preferences 
FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- Create refresh functions for materialized views
CREATE OR REPLACE FUNCTION refresh_consensus_views() 
RETURNS void AS 
BEGIN 
    REFRESH MATERIALIZED VIEW CONCURRENTLY mv_consensus_summary; 
    REFRESH MATERIALIZED VIEW CONCURRENTLY mv_firm_performance; 
    REFRESH MATERIALIZED VIEW CONCURRENTLY mv_consensus_impact_analysis; 
END; 
language 'plpgsql';

CREATE OR REPLACE FUNCTION schedule_consensus_view_refresh() 
RETURNS void AS 
BEGIN 
    PERFORM refresh_consensus_views(); 
END; 
language 'plpgsql';
