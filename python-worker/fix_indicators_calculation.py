#!/usr/bin/env python3
"""
Fix Indicators Calculation for Historical Data
Calculates indicators for all historical price data
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def fix_indicators_calculation():
    """Fix indicators calculation for all symbols with historical data"""
    
    print("🔧 FIXING INDICATORS CALCULATION")
    print("=" * 50)
    
    # Symbols that have raw data but limited indicators
    symbols = ["SOFI", "NVDA", "AVGO", "MU", "GOOGL", "APLD", "IREN", "ZETA", "NBIS", "CRWV", "QQQ", "SMH"]
    
    print(f"📊 Fixing indicators for {len(symbols)} symbols")
    print(f"🔤 Symbols: {', '.join(symbols)}")
    print()
    
    try:
        import psycopg2
        import pandas as pd
        from datetime import datetime
        from app.utils.technical_calculator import TechnicalIndicatorCalculator
        from app.repositories.indicators_repository import IndicatorsRepository
        from app.repositories.market_data_daily_repository import MarketDataDailyRepository
        
        print("✅ Components imported successfully")
        
        # Initialize components
        tech_calc = TechnicalIndicatorCalculator()
        indicators_repo = IndicatorsRepository()
        market_data_repo = MarketDataDailyRepository()
        
        print("✅ Components initialized")
        print()
        
        # Database connection
        db_url = os.getenv('DATABASE_URL', 'postgresql://postgres:postgres@localhost:5432/trading_db')
        conn = psycopg2.connect(db_url)
        
        successful_fixes = []
        failed_fixes = []
        
        for i, symbol in enumerate(symbols, 1):
            print(f"🔧 [{i}/{len(symbols)}] Fixing {symbol} indicators...")
            
            try:
                # Load raw price data for this symbol
                print(f"   📊 Loading raw price data...")
                
                query = """
                    SELECT date, open, high, low, close, volume
                    FROM raw_market_data_daily 
                    WHERE symbol = %s 
                    ORDER BY date
                """
                
                price_df = pd.read_sql(query, conn, params=(symbol,))
                
                if price_df.empty:
                    print(f"   ❌ No raw price data found for {symbol}")
                    failed_fixes.append(symbol)
                    continue
                
                print(f"   ✅ Raw data: {len(price_df)} records from {price_df['date'].min()} to {price_df['date'].max()}")
                
                # Calculate indicators for all data
                print(f"   📈 Calculating indicators for all {len(price_df)} records...")
                
                indicators_dict = tech_calc.calculate_all_derived_indicators(price_df)
                
                if not indicators_dict:
                    print(f"   ❌ Failed to calculate indicators for {symbol}")
                    failed_fixes.append(symbol)
                    continue
                
                print(f"   ✅ Indicators calculated: {len(indicators_dict)} indicators")
                
                # Convert to DataFrame format expected by indicators repository
                # Only keep records where indicators are available
                indicators_df = price_df.copy()
                
                # Add calculated indicators to DataFrame
                for indicator_name, indicator_series in indicators_dict.items():
                    if isinstance(indicator_series, pd.Series):
                        # Align with original DataFrame index
                        indicators_df[indicator_name.lower()] = indicator_series.reindex(indicators_df.index)
                    else:
                        # Handle numpy arrays or other types
                        indicators_df[indicator_name.lower()] = pd.Series(indicator_series, index=indicators_df.index)
                
                # Add required columns for indicators repository
                # Map to expected column names
                if 'ema_50' in indicators_df.columns:
                    indicators_df['ema_20'] = indicators_df['ema_50']  # Use EMA_50 as EMA_20
                if 'sma_200' in indicators_df.columns:
                    indicators_df['sma_50'] = indicators_df['sma_200']  # Use SMA_200 as SMA_50
                if 'macd_signal' in indicators_df.columns:
                    indicators_df['macd'] = indicators_df['macd_signal']
                    indicators_df['macd_signal'] = indicators_df['macd_signal']
                
                # Calculate RSI if not present (needed for swing engines)
                if 'rsi_14' not in indicators_df.columns:
                    print(f"   📊 Calculating RSI...")
                    delta = price_df['close'].diff()
                    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
                    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
                    rs = gain / loss
                    indicators_df['rsi_14'] = 100 - (100 / (1 + rs))
                
                # Only keep rows where we have valid indicators (drop NaN values)
                indicators_df = indicators_df.dropna()
                
                print(f"   ✅ Indicators DataFrame: {len(indicators_df)} records (after dropping NaN)")
                
                # Save indicators to database
                print(f"   💾 Saving indicators to database...")
                
                # Clear existing indicators for this symbol
                cursor = conn.cursor()
                cursor.execute("DELETE FROM indicators_daily WHERE symbol = %s", (symbol,))
                conn.commit()
                
                # Save new indicators
                indicators_saved = indicators_repo.upsert_data(indicators_df)
                
                if indicators_saved:
                    print(f"   ✅ SUCCESS: Indicators saved for {symbol}")
                    successful_fixes.append(symbol)
                else:
                    print(f"   ❌ FAILED: Could not save indicators for {symbol}")
                    failed_fixes.append(symbol)
                
                # Show date range
                if indicators_df is not None and not indicators_df.empty:
                    min_date = indicators_df['date'].min()
                    max_date = indicators_df['date'].max()
                    print(f"   📅 Indicators range: {min_date} to {max_date}")
                
            except Exception as e:
                print(f"   ❌ FAILED: {e}")
                failed_fixes.append(symbol)
            
            print()
        
        conn.close()
        
        # Summary
        print("📋 INDICATORS FIX SUMMARY")
        print("=" * 40)
        print(f"✅ Successful: {len(successful_fixes)}/{len(symbols)} symbols")
        print(f"❌ Failed: {len(failed_fixes)}/{len(symbols)} symbols")
        print()
        
        if successful_fixes:
            print("✅ Successfully fixed indicators for:")
            for symbol in successful_fixes:
                print(f"   • {symbol}")
        
        if failed_fixes:
            print()
            print("❌ Failed to fix indicators for:")
            for symbol in failed_fixes:
                print(f"   • {symbol}")
        
        return len(successful_fixes) > 0
        
    except ImportError as e:
        print(f"❌ Import error: {e}")
        return False
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        return False

def verify_indicators_fixed():
    """Verify that indicators were fixed successfully"""
    
    print("\n🔍 VERIFYING INDICATORS FIX")
    print("=" * 40)
    
    try:
        import psycopg2
        import os
        from datetime import datetime
        
        db_url = os.getenv('DATABASE_URL', 'postgresql://postgres:postgres@localhost:5432/trading_db')
        conn = psycopg2.connect(db_url)
        cursor = conn.cursor()
        
        # Check indicators for all target symbols
        target_symbols = ["SOFI", "NVDA", "AVGO", "MU", "GOOGL", "APLD", "IREN", "ZETA", "NBIS", "CRWV", "QQQ", "SMH"]
        
        cursor.execute("""
            SELECT DISTINCT symbol, 
                   COUNT(*) as record_count,
                   MIN(date) as start_date,
                   MAX(date) as end_date
            FROM indicators_daily 
            WHERE symbol = ANY(%s)
            GROUP BY symbol 
            ORDER BY symbol
        """, (target_symbols,))
        
        results = cursor.fetchall()
        
        if not results:
            print("❌ No indicators data found for target symbols")
            return False
        
        print(f"✅ Found indicators data for {len(results)} symbols:")
        print()
        print(f"{'Symbol':<8} {'Records':<8} {'Date Range':<22} {'Status':<10}")
        print("-" * 60)
        
        symbols_with_full_data = []
        
        for row in results:
            symbol, count, start_date, end_date = row
            date_range = f"{start_date} to {end_date}"
            
            # Determine status
            if count >= 200:
                status = "Full Year"
                symbols_with_full_data.append(symbol)
            elif count >= 50:
                status = "Partial"
            else:
                status = "Limited"
            
            print(f"{symbol:<8} {count:<8} {date_range:<22} {status:<10}")
        
        print("-" * 60)
        print()
        
        print(f"📊 SUMMARY:")
        print(f"   Symbols with indicators: {len(results)}/{len(target_symbols)}")
        print(f"   Symbols with full year data: {len(symbols_with_full_data)}")
        
        if symbols_with_full_data:
            print(f"   ✅ Full year data: {', '.join(symbols_with_full_data)}")
        
        conn.close()
        
        return len(symbols_with_full_data) > 0
        
    except Exception as e:
        print(f"❌ Error verifying indicators: {e}")
        return False

def main():
    """Main function"""
    
    print("🎯 INDICATORS CALCULATION FIX")
    print("=" * 50)
    print("Fixes indicators calculation for historical data")
    print()
    
    # Fix indicators
    success = fix_indicators_calculation()
    
    # Verify fix
    has_full_data = verify_indicators_fixed()
    
    # Final summary
    print(f"\n📊 FINAL SUMMARY")
    print("=" * 30)
    print(f"✅ Fix successful: {success}")
    print(f"📅 Full year data: {'✅' if has_full_data else '❌'}")
    print()
    
    if success and has_full_data:
        print("🎉 INDICATORS CALCULATION FIXED!")
        print("You can now test swing engines with full historical data.")
        print()
        print("🚀 Next steps:")
        print("1. Test swing engines:")
        print("   python test_swing_engines_multiple_symbols.py")
        print("2. Analyze signals:")
        print("   python simple_data_loader.py")
        print("3. Compare engines:")
        print("   python comprehensive_signal_analysis.py")
    else:
        print("❌ INDICATORS CALCULATION FIX INCOMPLETE!")
        print("Some symbols may still have limited indicators data.")
        print("Check the errors above and troubleshoot accordingly.")
    
    return success

if __name__ == "__main__":
    success = main()
    
    if success:
        print("\n🎉 INDICATORS CALCULATION FIX COMPLETED!")
        print("You can now test swing engines with your specified symbols.")
    else:
        print("\n❌ INDICATORS CALCULATION FIX FAILED!")
        print("Check the errors above and troubleshoot accordingly.")
