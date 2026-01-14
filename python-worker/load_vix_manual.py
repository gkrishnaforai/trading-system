#!/usr/bin/env python3
"""
Manual VIX Data Loader
Loads current VIX data from Yahoo Finance into macro_market_data table
"""

import os
import sys
import psycopg2
from datetime import date, datetime
from dotenv import load_dotenv

def load_vix_data():
    """Load current VIX data from Yahoo Finance"""
    
    load_dotenv()
    database_url = os.getenv('DATABASE_URL')
    
    if not database_url:
        print("❌ DATABASE_URL not found")
        return False
    
    print("📈 Loading VIX Data from Yahoo Finance...")
    
    try:
        # Import yfinance
        import yfinance as yf
        
        # Download VIX data
        print("📥 Fetching VIX data...")
        vix = yf.Ticker("^VIX")
        
        # Get recent data (last 7 days)
        end_date = datetime.now()
        start_date = end_date - timedelta(days=7)
        
        vix_data = vix.history(start=start_date, end=end_date)
        
        if vix_data.empty:
            print("❌ No VIX data received")
            return False
        
        print(f"📊 Got {len(vix_data)} days of VIX data")
        
        # Connect to database
        conn = psycopg2.connect(database_url)
        conn.autocommit = True
        cursor = conn.cursor()
        
        # Insert VIX data
        records_added = 0
        for index, row in vix_data.iterrows():
            data_date = index.date()
            vix_close = float(row['Close'])
            
            # Check if already exists
            cursor.execute("""
                SELECT EXISTS (
                    SELECT 1 FROM macro_market_data 
                    WHERE data_date = %s
                )
            """, (data_date,))
            
            if not cursor.fetchone()[0]:
                # Insert new record
                cursor.execute("""
                    INSERT INTO macro_market_data 
                    (data_date, vix_close, source, created_at)
                    VALUES (%s, %s, 'yahoo_finance', CURRENT_TIMESTAMP)
                """, (data_date, vix_close))
                
                records_added += 1
                print(f"   ✅ Added VIX {vix_close:.2f} for {data_date}")
        
        cursor.close()
        conn.close()
        
        print(f"🎉 Successfully added {records_added} VIX records!")
        return True
        
    except ImportError:
        print("❌ yfinance not available. Install with: pip install yfinance")
        return False
    except Exception as e:
        print(f"❌ Error loading VIX data: {e}")
        return False

if __name__ == "__main__":
    from datetime import timedelta
    
    success = load_vix_data()
    
    if success:
        print("\n📋 Next Steps:")
        print("1. Check VIX data:")
        print("   curl http://localhost:8001/admin/data-summary/macro_market_data")
        print("2. Test stock analysis (will include VIX):")
        print("   curl -X POST http://localhost:8001/api/v1/universal/backtest \\")
        print("        -H 'Content-Type: application/json' \\")
        print("        -d '{\"symbol\": \"AAPL\", \"analysis_type\": \"comprehensive\"}'")
    else:
        print("❌ Failed to load VIX data")
        sys.exit(1)
