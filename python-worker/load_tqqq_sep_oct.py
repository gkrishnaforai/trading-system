#!/usr/bin/env python3
"""
Load TQQQ historical data for September and October 2025
"""

import sys
import os
import pandas as pd
from datetime import datetime, timedelta
sys.path.append('/app')

def load_tqqq_historical_data():
    """Load TQQQ historical data for Sep-Oct 2025"""
    
    print("📈 Loading TQQQ Historical Data for Sep-Oct 2025")
    print("=" * 60)
    
    try:
        import yfinance as yf
        from app.database import db
        
        # Download TQQQ data
        print("📥 Downloading TQQQ data from Yahoo Finance...")
        tqqq = yf.Ticker("TQQQ")
        
        # Get data for September and October 2025
        start_date = datetime(2025, 1, 1)
        end_date = datetime(2025, 8, 31)
        
        tqqq_data = tqqq.history(start=start_date, end=end_date)
        
        print(f"✅ Downloaded {len(tqqq_data)} days of TQQQ data")
        print(f"📅 Date range: {tqqq_data.index[0].date()} to {tqqq_data.index[-1].date()}")
        
        # Prepare data for database
        records_to_insert = []
        
        for date, row in tqqq_data.iterrows():
            # Store in raw_market_data_daily table
            records_to_insert.append({
                'symbol': 'TQQQ',
                'date': date.date(),
                'open': float(row['Open']),
                'high': float(row['High']),
                'low': float(row['Low']),
                'close': float(row['Close']),
                'volume': int(row.get('Volume', 0)),
                'adjusted_close': float(row['Close']),  # TQQQ doesn't have adjusted close
                'data_source': 'yahoo_finance',
                'created_at': datetime.now()
            })
        
        # Clear existing TQQQ data for Sep-Oct 2025
        print("🗑️ Clearing existing TQQQ data for Sep-Oct 2025...")
        db.execute_update("""
            DELETE FROM raw_market_data_daily 
            WHERE symbol = 'TQQQ' 
            AND date >= '2025-09-01' 
            AND date <= '2025-10-31'
        """)
        
        # Insert new data
        print("💾 Inserting TQQQ data...")
        
        for record in records_to_insert:
            insert_query = """
                INSERT INTO raw_market_data_daily (
                    symbol, date, open, high, low, close, volume, 
                    adjusted_close, data_source, created_at
                ) VALUES (
                    :symbol, :date, :open, :high, :low, :close, :volume,
                    :adjusted_close, :data_source, :created_at
                )
            """
            db.execute_update(insert_query, record)
        
        print(f"✅ Successfully inserted {len(records_to_insert)} TQQQ records")
        
        # Verify the data
        verify_query = """
            SELECT COUNT(*) as total_records,
                   MIN(date) as earliest_date,
                   MAX(date) as latest_date,
                   AVG(close) as avg_close,
                   MIN(close) as min_close,
                   MAX(close) as max_close
            FROM raw_market_data_daily 
            WHERE symbol = 'TQQQ' 
            AND date >= '2025-09-01' 
            AND date <= '2025-10-31'
        """
        
        result = db.execute_query(verify_query)
        if result:
            row = result[0]
            print(f"📊 Verification:")
            print(f"  Total records: {row['total_records']}")
            print(f"  Date range: {row['earliest_date']} to {row['latest_date']}")
            print(f"  Average close: ${row['avg_close']:.2f}")
            print(f"  Price range: ${row['min_close']:.2f} - ${row['max_close']:.2f}")
        
        # Get recent TQQQ values for context
        recent_query = """
            SELECT date, close 
            FROM raw_market_data_daily 
            WHERE symbol = 'TQQQ' 
            AND date >= '2025-09-01' 
            AND date <= '2025-10-31'
            ORDER BY date DESC 
            LIMIT 5
        """
        
        recent_data = db.execute_query(recent_query)
        print(f"\n📈 Recent TQQQ values (Sep-Oct 2025):")
        for row in recent_data:
            print(f"  {row['date']}: ${row['close']:.2f}")
        
        # Check total TQQQ data availability
        total_query = """
            SELECT COUNT(*) as total,
                   MIN(date) as earliest,
                   MAX(date) as latest
            FROM raw_market_data_daily 
            WHERE symbol = 'TQQQ'
        """
        
        total_result = db.execute_query(total_query)
        if total_result:
            total_row = total_result[0]
            print(f"\n📊 Total TQQQ data in database:")
            print(f"  Total records: {total_row['total']}")
            print(f"  Full date range: {total_row['earliest']} to {total_row['latest']}")
        
        print(f"\n🎉 TQQQ Sep-Oct 2025 data loading complete!")
        print(f"Now November backtesting should have proper historical context")
        
    except ImportError:
        print("❌ yfinance not available. Installing...")
        os.system("pip install yfinance")
        print("🔄 Please run the script again after installation")
        
    except Exception as e:
        print(f"❌ Error loading TQQQ data: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    load_tqqq_historical_data()
