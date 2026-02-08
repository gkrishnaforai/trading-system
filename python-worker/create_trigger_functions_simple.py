#!/usr/bin/env python3
"""
Simple Trigger Functions Creator
Follows the same pattern as run_column_migration.py
"""

import os
import sys
import psycopg2
from psycopg2 import OperationalError
from dotenv import load_dotenv

def create_trigger_functions():
    """Create trigger functions using simple psycopg2 approach"""
    
    # Load environment variables
    load_dotenv()
    
    # Get database connection string
    database_url = os.getenv('DATABASE_URL')
    if not database_url:
        print("❌ DATABASE_URL not found in environment variables")
        return False
    
    print("🔧 Creating Trigger Functions...")
    print("=" * 60)
    
    try:
        # Connect to PostgreSQL database
        print("📡 Connecting to database...")
        conn = psycopg2.connect(database_url)
        conn.autocommit = True
        cursor = conn.cursor()
        
        # Simple trigger function definitions
        trigger_functions_sql = """
-- Create function to update updated_at
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Create trigger for grade change events
CREATE OR REPLACE FUNCTION trigger_grade_change_event()
RETURNS TRIGGER AS $$
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
$$ LANGUAGE plpgsql;

-- Create trigger for consensus change events
CREATE OR REPLACE FUNCTION trigger_consensus_change_event()
RETURNS TRIGGER AS $$
BEGIN
    IF OLD.consensus_rating IS DISTINCT FROM NEW.consensus_rating THEN
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
            END
        );
        
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
        PERFORM pg_notify('consensus_change', NEW.symbol || '|' || 
            CASE 
                WHEN OLD.consensus_rating IS NULL THEN 'initiate'
                WHEN NEW.consensus_rating > OLD.consensus_rating THEN 'upgrade'
                WHEN NEW.consensus_rating < OLD.consensus_rating THEN 'downgrade'
                ELSE 'maintain'
            END);
    END IF;
    
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Create trigger for alert queue processing
CREATE OR REPLACE FUNCTION queue_consensus_alert()
RETURNS TRIGGER AS $$
BEGIN
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
        
        PERFORM pg_notify('consensus_alert', NEW.symbol || '|' || NEW.consensus_change);
    END IF;
    
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
"""
        
        print("🔨 Creating trigger functions...")
        cursor.execute(trigger_functions_sql)
        print("✅ Trigger functions created successfully!")
        
        # Create triggers
        triggers_sql = """
-- Create triggers for existing tables
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

-- Note: Triggers for tables created in migrations will be created after migrations
-- user_stock_alert_preferences and consensus_alert_queue triggers will be created separately
"""
        
        print("🔨 Creating triggers...")
        cursor.execute(triggers_sql)
        print("✅ Triggers created successfully!")
        
        # Close connection
        cursor.close()
        conn.close()
        
        print("\n🎉 Trigger functions and triggers completed!")
        return True
        
    except OperationalError as e:
        print(f"❌ Database connection error: {e}")
        return False
        
    except Exception as e:
        print(f"❌ Error creating triggers: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    """Main function"""
    success = create_trigger_functions()
    
    if success:
        print("\n✅ Trigger functions setup completed!")
        sys.exit(0)
    else:
        print("\n❌ Trigger functions failed!")
        sys.exit(1)

if __name__ == "__main__":
    main()
