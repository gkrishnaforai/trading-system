#!/usr/bin/env python3
"""
Check what tables exist in the database
"""
import sys
import os

# Add the project root to Python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.database import db
from sqlalchemy import text

def check_tables():
    """Check which Alpha Vantage tables exist"""
    print("🔍 CHECKING DATABASE TABLES")
    print("=" * 30)
    
    try:
        db.initialize()
        
        with db.get_session() as session:
            # Get all tables in the database
            result = session.execute(text("""
                SELECT table_name 
                FROM information_schema.tables 
                WHERE table_schema = 'public' 
                ORDER BY table_name
            """)).fetchall()
            
            print("📋 All tables in database:")
            for row in result:
                table_name = row[0]
                print(f"   • {table_name}")
            
            # Check specific Alpha Vantage tables
            av_tables = [
                'fundamentals_summary',
                'fundamentals',
                'raw_market_data_daily', 
                'indicators_daily',
                'data_ingestion_state',
                'industry_peers'
            ]
            
            print(f"\n🎯 Alpha Vantage Tables Status:")
            for table in av_tables:
                try:
                    result = session.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar()
                    print(f"✅ {table}: {result} records")
                except Exception as e:
                    print(f"❌ {table}: MISSING - {str(e)[:50]}...")
    
    except Exception as e:
        print(f"❌ Error checking tables: {e}")

if __name__ == "__main__":
    check_tables()
