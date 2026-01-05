#!/usr/bin/env python3
"""
Check Available Symbols in Database
Shows what symbols currently have data in the database
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def check_available_symbols():
    """Check what symbols are available in the database"""
    
    print("🔍 CHECKING AVAILABLE SYMBOLS IN DATABASE")
    print("=" * 50)
    
    try:
        import psycopg2
        import os
        
        db_url = os.getenv('DATABASE_URL', 'postgresql://postgres:postgres@localhost:5432/trading_db')
        
        conn = psycopg2.connect(db_url)
        cursor = conn.cursor()
        
        # Get symbols from indicators_daily
        cursor.execute("""
            SELECT DISTINCT symbol, 
                   COUNT(*) as record_count,
                   MIN(date) as start_date,
                   MAX(date) as end_date
            FROM indicators_daily 
            GROUP BY symbol 
            ORDER BY symbol
        """)
        
        symbols = cursor.fetchall()
        
        if not symbols:
            print("❌ No symbols found in indicators_daily table")
            print()
            print("🔧 SOLUTION:")
            print("1. Load historical data first:")
            print("   python load_specified_symbols.py")
            print("2. Or use the Streamlit dashboard to load data")
            return
        
        print(f"✅ Found {len(symbols)} symbols with data:")
        print()
        print(f"{'Symbol':<8} {'Records':<8} {'Date Range':<22} {'Days':<6}")
        print("-" * 50)
        
        total_records = 0
        
        for symbol, count, start_date, end_date in symbols:
            date_range = f"{start_date} to {end_date}"
            days = (end_date - start_date).days + 1 if start_date and end_date else 0
            print(f"{symbol:<8} {count:<8} {date_range:<22} {days:<6}")
            total_records += count
        
        print("-" * 50)
        print(f"{'TOTAL':<8} {total_records:<8} {'':<22} {'':<6}")
        print()
        
        # Check for your specific symbols
        target_symbols = ['SOFI', 'NVDA', 'AVGO', 'MU', 'GOOGL', 'APLD', 'IREN', 'ZETA', 'NBIS', 'CRWV', 'QQQ', 'SMH']
        available_symbols = [s[0] for s in symbols]
        
        print("🎯 TARGET SYMBOLS STATUS:")
        print("-" * 30)
        
        available_targets = []
        missing_targets = []
        
        for symbol in target_symbols:
            if symbol in available_symbols:
                available_targets.append(symbol)
                print(f"✅ {symbol}")
            else:
                missing_targets.append(symbol)
                print(f"❌ {symbol}")
        
        print()
        
        if available_targets:
            print(f"✅ {len(available_targets)} target symbols available")
            print("🚀 You can test swing engines with these symbols:")
            print(f"   python simple_data_loader.py")
            print(f"   python test_swing_engines_multiple_symbols.py")
        
        if missing_targets:
            print(f"❌ {len(missing_targets)} target symbols missing")
            print("🔧 Load missing data:")
            print(f"   python load_specified_symbols.py")
        
        conn.close()
        
        return len(available_targets) > 0
        
    except Exception as e:
        print(f"❌ Error checking database: {e}")
        return False

if __name__ == "__main__":
    check_available_symbols()
