#!/usr/bin/env python3
"""
Database Initialization Script
Run this to recreate the entire database schema from scratch
"""

import os
import sys
import psycopg2
from psycopg2 import OperationalError
from dotenv import load_dotenv

def load_database_schema():
    """Load the complete database schema from SQL file"""
    
    # Load environment variables
    load_dotenv()
    
    # Get database connection string
    database_url = os.getenv('DATABASE_URL')
    if not database_url:
        print("❌ DATABASE_URL not found in environment variables")
        return False
    
    print("🚀 Initializing Trading System Database...")
    print("=" * 60)
    
    try:
        # Connect to PostgreSQL database
        print("📡 Connecting to database...")
        conn = psycopg2.connect(database_url)
        conn.autocommit = True  # Enable autocommit for DDL statements
        cursor = conn.cursor()
        
        # Get the SQL file path
        current_dir = os.path.dirname(os.path.abspath(__file__))
        sql_file = os.path.join(current_dir, 'migrations', 'init_database_complete.sql')
        
        if not os.path.exists(sql_file):
            print(f"❌ SQL file not found: {sql_file}")
            return False
        
        print(f"📄 Reading schema from: {sql_file}")
        
        # Read and execute the SQL file
        with open(sql_file, 'r') as file:
            sql_content = file.read()
        
        print("🔨 Creating database schema...")
        cursor.execute(sql_content)
        
        print("✅ Database schema created successfully!")
        
        # Verify key tables exist
        cursor.execute("""
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = 'public' 
            ORDER BY table_name
        """)
        tables = [row[0] for row in cursor.fetchall()]
        
        print(f"📊 Created {len(tables)} tables:")
        for table in tables:
            print(f"   ✅ {table}")
        
        # Close connection
        cursor.close()
        conn.close()
        
        print("\n🎉 Database initialization complete!")
        print("🔄 You can now restart the python-worker service")
        
        return True
        
    except OperationalError as e:
        print(f"❌ Database connection error: {e}")
        print("🔧 Please check your DATABASE_URL configuration")
        return False
        
    except Exception as e:
        print(f"❌ Error creating database schema: {e}")
        return False

def main():
    """Main function"""
    success = load_database_schema()
    
    if success:
        print("\n📋 Next Steps:")
        print("1. Restart the python-worker service:")
        print("   docker-compose restart python-worker")
        print("2. Run bulk stock loading:")
        print("   curl -X POST http://localhost:8001/api/v1/bulk/stocks/load/popular")
        print("3. Test the Streamlit UI - stock selector should work!")
        sys.exit(0)
    else:
        print("\n❌ Database initialization failed!")
        sys.exit(1)

if __name__ == "__main__":
    main()
