#!/usr/bin/env python3
"""
Create remaining triggers for tables created in migrations
"""

import os
import sys
import psycopg2
from psycopg2 import OperationalError
from dotenv import load_dotenv

def create_remaining_triggers():
    """Create triggers for tables created in migrations"""
    
    # Load environment variables
    load_dotenv()
    
    # Get database connection string
    database_url = os.getenv('DATABASE_URL')
    if not database_url:
        print("❌ DATABASE_URL not found in environment variables")
        return False
    
    print("🔧 Creating Remaining Triggers...")
    print("=" * 60)
    
    try:
        # Connect to PostgreSQL database
        print("📡 Connecting to database...")
        conn = psycopg2.connect(database_url)
        conn.autocommit = True
        cursor = conn.cursor()
        
        # Create triggers for tables created in migrations
        remaining_triggers_sql = """
-- Create trigger for consensus alert queue
DROP TRIGGER IF EXISTS queue_consensus_alert ON consensus_change_events;
CREATE TRIGGER queue_consensus_alert
AFTER INSERT ON consensus_change_events
FOR EACH ROW EXECUTE FUNCTION queue_consensus_alert();

-- Create trigger for user stock alert preferences
DROP TRIGGER IF EXISTS update_user_stock_alert_preferences_updated_at ON user_stock_alert_preferences;
CREATE TRIGGER update_user_stock_alert_preferences_updated_at 
BEFORE UPDATE ON user_stock_alert_preferences 
FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
"""
        
        print("🔨 Creating remaining triggers...")
        cursor.execute(remaining_triggers_sql)
        print("✅ Remaining triggers created successfully!")
        
        # Close connection
        cursor.close()
        conn.close()
        
        print("\n🎉 All triggers completed!")
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
    success = create_remaining_triggers()
    
    if success:
        print("\n✅ Remaining triggers setup completed!")
        sys.exit(0)
    else:
        print("\n❌ Remaining triggers failed!")
        sys.exit(1)

if __name__ == "__main__":
    main()
