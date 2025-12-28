#!/usr/bin/env python3
"""
Load Alpha Vantage Earnings Calendar from Local CSV File
Loads earnings data from ~/Downloads/earnings_calendar.csv into database
"""
import sys
import os
import csv
from datetime import datetime

# Add the project root to Python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.database import db
from app.observability.logging import get_logger
from sqlalchemy import text

logger = get_logger("load_earnings_from_csv")

def create_earnings_calendar_table():
    """Create earnings_calendar table if it doesn't exist"""
    try:
        with db.get_session() as session:
            # Create earnings_calendar table
            session.execute(text("""
                CREATE TABLE IF NOT EXISTS earnings_calendar (
                    id SERIAL PRIMARY KEY,
                    symbol VARCHAR(10) NOT NULL,
                    company_name VARCHAR(255),
                    report_date DATE NOT NULL,
                    estimated_eps NUMERIC(10, 4),
                    currency VARCHAR(10),
                    horizon VARCHAR(20) DEFAULT '3month',
                    data_source VARCHAR(50) DEFAULT 'alphavantage',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(symbol, report_date, data_source)
                )
            """))
            
            # Create indexes
            session.execute(text("CREATE INDEX IF NOT EXISTS idx_earnings_calendar_symbol ON earnings_calendar(symbol)"))
            session.execute(text("CREATE INDEX IF NOT EXISTS idx_earnings_calendar_report_date ON earnings_calendar(report_date)"))
            session.execute(text("CREATE INDEX IF NOT EXISTS idx_earnings_calendar_symbol_date ON earnings_calendar(symbol, report_date)"))
            session.execute(text("CREATE INDEX IF NOT EXISTS idx_earnings_calendar_horizon ON earnings_calendar(horizon)"))
            
            # Add comment
            session.execute(text("COMMENT ON TABLE earnings_calendar IS 'Upcoming earnings calendar from Alpha Vantage'"))
            
            session.commit()
            logger.info("✅ Earnings calendar table created/verified")
            return True
            
    except Exception as e:
        logger.error(f"Error creating earnings_calendar table: {e}")
        return False

def load_earnings_from_csv(csv_file_path: str):
    """Load earnings data from CSV file into database"""
    print(f"📅 LOADING EARNINGS CALENDAR FROM CSV")
    print("=" * 45)
    print(f"File: {csv_file_path}")
    
    try:
        # Initialize database
        db.initialize()
        print("✅ Database initialized")
        
        # Create table
        if not create_earnings_calendar_table():
            return False
        
        # Read CSV file
        print(f"\n📖 Reading CSV file...")
        with open(csv_file_path, 'r', encoding='utf-8') as file:
            csv_reader = csv.reader(file)
            
            # Get headers
            headers = next(csv_reader)
            print(f"✅ CSV headers: {headers}")
            
            # Read data rows
            rows = list(csv_reader)
            print(f"✅ Found {len(rows)} earnings records")
            
            if len(rows) == 0:
                print("❌ No data rows found in CSV")
                return False
        
        # Transform data for database
        print(f"\n🔄 Transforming data...")
        records = []
        
        for row in rows:
            if len(row) >= 4:  # Ensure we have enough columns
                record = {
                    'symbol': row[0].strip(),
                    'company_name': row[1].strip(),
                    'report_date': parse_date(row[2].strip()),
                    'estimated_eps': parse_float(row[3].strip()),
                    'currency': row[4].strip() if len(row) > 4 else 'USD',
                    'horizon': '3month',
                    'data_source': 'alphavantage',
                    'created_at': datetime.now(),
                    'updated_at': datetime.now()
                }
                records.append(record)
        
        print(f"✅ Transformed {len(records)} records")
        
        # Save to database
        print(f"\n💾 Saving to database...")
        with db.get_session() as session:
            for i, record in enumerate(records):
                try:
                    # Use UPSERT to avoid duplicates
                    session.execute(text("""
                        INSERT INTO earnings_calendar (
                            symbol, company_name, report_date, estimated_eps, currency,
                            horizon, data_source, created_at, updated_at
                        ) VALUES (
                            :symbol, :company_name, :report_date, :estimated_eps, :currency,
                            :horizon, :data_source, :created_at, :updated_at
                        ) ON CONFLICT (symbol, report_date, data_source) 
                        DO UPDATE SET
                            company_name = EXCLUDED.company_name,
                            estimated_eps = EXCLUDED.estimated_eps,
                            currency = EXCLUDED.currency,
                            horizon = EXCLUDED.horizon,
                            updated_at = EXCLUDED.updated_at
                        """), record)
                    
                    # Progress indicator
                    if (i + 1) % 100 == 0:
                        print(f"   Processed {i + 1}/{len(records)} records...")
                
                except Exception as e:
                    print(f"⚠️  Error processing record {i}: {e}")
                    continue
            
            session.commit()
            print(f"✅ Saved {len(records)} records to database")
        
        # Verify data
        print(f"\n🔍 Verifying loaded data...")
        with db.get_session() as session:
            total_count = session.execute(text("SELECT COUNT(*) FROM earnings_calendar")).scalar()
            unique_symbols = session.execute(text("SELECT COUNT(DISTINCT symbol) FROM earnings_calendar")).scalar()
            
            print(f"✅ Total records: {total_count}")
            print(f"✅ Unique symbols: {unique_symbols}")
            
            # Show date range
            date_range = session.execute(text("""
                SELECT MIN(report_date), MAX(report_date) FROM earnings_calendar
            """)).fetchone()
            
            if date_range and date_range[0]:
                print(f"✅ Date range: {date_range[0]} to {date_range[1]}")
            
            # Show sample data
            sample = session.execute(text("""
                SELECT symbol, company_name, report_date, estimated_eps, currency
                FROM earnings_calendar 
                ORDER BY report_date ASC 
                LIMIT 5
            """)).fetchall()
            
            if sample:
                print(f"\n📊 Sample earnings data:")
                for i, row in enumerate(sample):
                    print(f"   {i+1}. {row[0]} - {row[1]}")
                    print(f"      Date: {row[2]}, EPS Estimate: {row[3]}, Currency: {row[4]}")
        
        print(f"\n🎉 EARNINGS CALENDAR LOADING COMPLETED!")
        print(f"✅ Successfully loaded {len(records)} earnings records")
        print(f"✅ Data ready for analysis and querying")
        
        return True
        
    except Exception as e:
        print(f"❌ Error loading earnings from CSV: {e}")
        return False

def parse_date(date_str: str):
    """Parse date string in various formats"""
    if not date_str or date_str.lower() == 'none':
        return None
    
    try:
        # Try different date formats
        formats = ['%Y-%m-%d', '%m/%d/%Y', '%d-%m-%Y', '%Y%m%d']
        
        for fmt in formats:
            try:
                return datetime.strptime(date_str, fmt)
            except ValueError:
                continue
        
        # If none of the formats work, return None
        return None
        
    except Exception:
        return None

def parse_float(value_str: str):
    """Parse float string"""
    if not value_str or value_str.lower() in ['none', 'nan', '']:
        return None
    
    try:
        return float(value_str.replace(',', ''))
    except ValueError:
        return None

def main():
    """Main function"""
    print("🚀 ALPHA VANTAGE EARNINGS CALENDAR CSV LOADER")
    print("=" * 55)
    
    # Default CSV file path
    csv_file = os.path.expanduser("~/Downloads/earnings_calendar.csv")
    
    # Check if file exists
    if not os.path.exists(csv_file):
        print(f"❌ CSV file not found: {csv_file}")
        print(f"   Please download the earnings calendar CSV to ~/Downloads/")
        return False
    
    # Load earnings data
    success = load_earnings_from_csv(csv_file)
    
    if success:
        print(f"\n🎯 LOADING RESULT: SUCCESS!")
        print(f"✅ Earnings calendar data loaded from CSV")
        print(f"✅ Database table created and populated")
        print(f"✅ Ready for earnings analysis")
        
        print(f"\n📋 NEXT STEPS:")
        print(f"   1. Query upcoming earnings using the database")
        print(f"   2. Set up earnings alerts and notifications")
        print(f"   3. Integrate with trading strategies")
        
    else:
        print(f"\n❌ LOADING FAILED")
        print(f"   Check CSV file format and database connection")
    
    return success

if __name__ == "__main__":
    main()
