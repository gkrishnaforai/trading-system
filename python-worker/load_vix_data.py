#!/usr/bin/env python3
"""
Load VIX historical data from Yahoo Finance
"""

import sys
import os
import pandas as pd
from datetime import datetime, timedelta
sys.path.append('/app')

def load_vix_data():
    """Load VIX historical data from Yahoo Finance"""
    
    print("📈 Loading VIX Historical Data")
    print("=" * 50)
    
    try:
        import yfinance as yf
        from app.database import db
        
        # Download VIX data
        print("📥 Downloading VIX data from Yahoo Finance...")
        vix = yf.Ticker("^VIX")
        
        # Get data for the last 3 months
        end_date = datetime.now()
        start_date = end_date - timedelta(days=90)
        
        vix_data = vix.history(start=start_date, end=end_date)
        
        print(f"✅ Downloaded {len(vix_data)} days of VIX data")
        print(f"📅 Date range: {vix_data.index[0].date()} to {vix_data.index[-1].date()}")
        
        # Prepare data for database
        records_to_insert = []
        
        for date, row in vix_data.iterrows():
            # Store in raw_market_data_daily table
            records_to_insert.append({
                'symbol': '^VIX',
                'date': date.date(),
                'open': float(row['Open']),
                'high': float(row['High']),
                'low': float(row['Low']),
                'close': float(row['Close']),
                'volume': int(row.get('Volume', 0)),
                'adjusted_close': float(row['Close']),  # VIX doesn't have adjusted close
                'data_source': 'yahoo_finance',
                'created_at': datetime.now()
            })
        
        # Clear existing VIX data
        print("🗑️ Clearing existing VIX data...")
        db.execute_update("DELETE FROM raw_market_data_daily WHERE symbol = '^VIX'")
        
        # Insert new data
        print("💾 Inserting VIX data...")
        
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
        
        print(f"✅ Successfully inserted {len(records_to_insert)} VIX records")
        
        # Verify the data
        verify_query = """
            SELECT COUNT(*) as total_records,
                   MIN(date) as earliest_date,
                   MAX(date) as latest_date,
                   AVG(close) as avg_vix
            FROM raw_market_data_daily 
            WHERE symbol = '^VIX'
        """
        
        result = db.execute_query(verify_query)
        if result:
            row = result[0]
            print(f"📊 Verification:")
            print(f"  Total records: {row['total_records']}")
            print(f"  Date range: {row['earliest_date']} to {row['latest_date']}")
            print(f"  Average VIX: {row['avg_vix']:.2f}")
        
        # Get recent VIX values for context
        recent_query = """
            SELECT date, close 
            FROM raw_market_data_daily 
            WHERE symbol = '^VIX'
            ORDER BY date DESC 
            LIMIT 5
        """
        
        recent_data = db.execute_query(recent_query)
        print(f"\n📈 Recent VIX values:")
        for row in recent_data:
            print(f"  {row['date']}: {row['close']:.2f}")
        
        print(f"\n🎉 VIX data loading complete!")
        print(f"Now TQQQ engine can access VIX data for proper analysis")
        
    except ImportError:
        print("❌ yfinance not available. Installing...")
        os.system("pip install yfinance")
        print("🔄 Please run the script again after installation")
        
    except Exception as e:
        print(f"❌ Error loading VIX data: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    load_vix_data()
