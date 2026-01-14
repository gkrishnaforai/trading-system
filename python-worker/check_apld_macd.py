#!/usr/bin/env python3
"""
Check APLD MACD values in database
"""
import logging
from sqlalchemy import text
from app.database import db

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')

def check_apld_macd():
    """Check APLD MACD values specifically"""
    print("🔍 CHECKING APLD MACD VALUES")
    print("=" * 50)
    
    try:
        # Initialize database if needed
        if db.session_factory is None:
            db.initialize()
        
        with db.get_session() as session:
            # Check indicators_daily table structure first
            print("\n📊 INDICATORS_DAILY TABLE STRUCTURE")
            print("-" * 40)
            
            columns = session.execute(text("""
                SELECT column_name, data_type, is_nullable
                FROM information_schema.columns 
                WHERE table_name = 'indicators_daily' 
                ORDER BY ordinal_position
            """)).fetchall()
            
            available_columns = [col[0] for col in columns]
            print(f"Available columns: {available_columns}")
            
            # Check APLD data with available columns
            print("\n📊 APLD INDICATOR DATA")
            print("-" * 30)
            
            # Build query with existing columns
            if 'sma_20' in available_columns:
                sma_col = 'sma_20'
            elif 'sma20' in available_columns:
                sma_col = 'sma20'
            else:
                sma_col = 'NULL as sma_20'
                
            query = f"""
                SELECT symbol, date, rsi_14, {sma_col}, ema_20, sma_50, macd, macd_signal, macd_hist
                FROM indicators_daily 
                WHERE symbol = 'APLD' 
                ORDER BY date DESC 
                LIMIT 5
            """
            
            result = session.execute(text(query)).fetchall()
            
            if result:
                print(f"✅ Found {len(result)} APLD records:")
                for row in result:
                    print(f"\n📈 Date: {row[1]}")
                    print(f"   RSI: {row[2]:.2f}")
                    print(f"   SMA20: {'N/A' if row[3] is None else f'{row[3]:.2f}'}")
                    print(f"   EMA20: {row[4]:.2f}")
                    print(f"   SMA50: {row[5]:.2f}")
                    print(f"   MACD: {row[6]:.4f}")
                    print(f"   MACD Signal: {row[7]:.4f}")
                    print(f"   MACD Histogram: {row[8]:.4f}")
                    
                    # Check for data issues
                    if row[6] is not None and row[2] is not None and abs(row[6] - row[2]) < 0.01:  # MACD equals RSI
                        print(f"   🚨 ISSUE: MACD ({row[6]}) equals RSI ({row[2]}) - DATA ERROR!")
                    if row[7] is not None and row[5] is not None and abs(row[7] - row[5]) < 0.01:  # MACD Signal equals SMA50
                        print(f"   🚨 ISSUE: MACD Signal ({row[7]}) equals SMA50 ({row[5]}) - DATA ERROR!")
                    if row[6] is not None and (row[6] > 50 or row[6] < -50):  # Values too high for MACD
                        print(f"   🚨 ISSUE: MACD values too high for typical calculation")
            else:
                print("❌ No APLD data found in indicators_daily")
                
                # Check if APLD exists in raw data
                raw_result = session.execute(text("""
                    SELECT symbol, COUNT(*) as count
                    FROM raw_market_data_daily 
                    WHERE symbol = 'APLD' 
                    GROUP BY symbol
                """)).fetchall()
                
                if raw_result:
                    print(f"📊 APLD found in raw data: {raw_result[0][1]} records")
                else:
                    print("❌ APLD not found in raw data either")
            
            # Check other symbols for comparison
            print("\n📊 COMPARISON WITH OTHER SYMBOLS")
            print("-" * 40)
            
            other_symbols = session.execute(text("""
                SELECT symbol, rsi_14, macd, macd_signal
                FROM indicators_daily 
                WHERE symbol != 'APLD' 
                ORDER BY date DESC 
                LIMIT 5
            """)).fetchall()
            
            if other_symbols:
                print("Other symbols for MACD comparison:")
                for row in other_symbols:
                    print(f"   {row[0]}: RSI={row[1]:.2f}, MACD={row[2]:.4f}, Signal={row[3]:.4f}")
            else:
                print("No other symbols found")
    
    except Exception as e:
        print(f"❌ Database check failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    check_apld_macd()
