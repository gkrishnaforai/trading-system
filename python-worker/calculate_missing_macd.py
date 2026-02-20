#!/usr/bin/env python3
"""
Generic MACD Calculation Script
Calculates MACD indicators for all symbols with price data but missing MACD
"""

import sys
import os
import pandas as pd
from datetime import datetime

# Add project root so imports work
sys.path.insert(0, os.path.dirname(__file__))

from app.database import db
from app.indicators.momentum import calculate_macd
from sqlalchemy import text

def calculate_missing_macd():
    """Calculate MACD for all symbols that have price data but missing MACD indicators"""
    
    print("🔍 Finding symbols with missing MACD indicators...")
    
    try:
        with db.get_session() as session:
            # Find symbols that have price data but no MACD indicators
            query = """
                SELECT DISTINCT r.symbol
                FROM raw_market_data_daily r
                LEFT JOIN indicators_daily i ON i.symbol = r.symbol 
                WHERE i.macd IS NULL 
                AND i.symbol IS NOT NULL
                ORDER BY r.symbol
            """
            
            result = session.execute(text(query))
            symbols = [row[0] for row in result.fetchall()]
            
            print(f"📊 Found {len(symbols)} symbols with missing MACD indicators")
            
            if not symbols:
                print("✅ All symbols already have MACD indicators!")
                return
            
            # Process each symbol
            for i, symbol in enumerate(symbols, 1):
                print(f"\n[{i}/{len(symbols)}] Processing {symbol}...")
                
                try:
                    # Get price data for this symbol
                    price_query = """
                        SELECT date, close
                        FROM raw_market_data_daily 
                        WHERE symbol = :symbol 
                        ORDER BY date ASC
                    """
                    
                    price_result = session.execute(text(price_query), {'symbol': symbol})
                    price_rows = price_result.fetchall()
                    
                    if len(price_rows) < 26:
                        print(f"  ⚠️  Skipping {symbol}: insufficient data ({len(price_rows)} days, need 26+)")
                        continue
                    
                    # Create DataFrame and calculate MACD
                    df = pd.DataFrame(price_rows, columns=['date', 'close'])
                    macd_line, macd_signal, macd_hist = calculate_macd(df['close'])
                    
                    # Update indicators table with MACD values
                    updated_count = 0
                    for j, (date, close) in enumerate(price_rows):
                        if (pd.notna(macd_line.iloc[j]) and 
                            pd.notna(macd_signal.iloc[j]) and 
                            pd.notna(macd_hist.iloc[j])):
                            
                            # Check if indicator row exists
                            check_query = """
                                SELECT 1 FROM indicators_daily 
                                WHERE symbol = :symbol AND date = :date
                            """
                            exists_result = session.execute(text(check_query), {
                                'symbol': symbol, 'date': date
                            })
                            indicator_exists = exists_result.fetchone() is not None
                            
                            if indicator_exists:
                                # Update existing row
                                update_query = """
                                    UPDATE indicators_daily 
                                    SET macd = :macd, 
                                        macd_signal = :macd_signal, 
                                        macd_hist = :macd_hist,
                                        updated_at = NOW()
                                    WHERE symbol = :symbol AND date = :date
                                """
                            else:
                                # Insert new row (shouldn't happen if data loading worked correctly)
                                update_query = """
                                    INSERT INTO indicators_daily 
                                    (symbol, date, macd, macd_signal, macd_hist, updated_at)
                                    VALUES (:symbol, :date, :macd, :macd_signal, :macd_hist, NOW())
                                """
                            
                            session.execute(text(update_query), {
                                'macd': float(macd_line.iloc[j]),
                                'macd_signal': float(macd_signal.iloc[j]), 
                                'macd_hist': float(macd_hist.iloc[j]),
                                'symbol': symbol,
                                'date': date
                            })
                            updated_count += 1
                    
                    session.commit()
                    print(f"  ✅ Updated {updated_count} MACD records for {symbol}")
                    
                except Exception as e:
                    print(f"  ❌ Error processing {symbol}: {e}")
                    session.rollback()
                    continue
            
            print(f"\n🎉 MACD calculation completed!")
            
            # Show summary
            summary_query = """
                SELECT 
                    COUNT(DISTINCT i.symbol) as symbols_with_macd,
                    COUNT(i.macd) as total_macd_records,
                    COUNT(DISTINCT r.symbol) as total_symbols_with_price
                FROM raw_market_data_daily r
                LEFT JOIN indicators_daily i ON i.symbol = r.symbol AND i.macd IS NOT NULL
            """
            
            summary_result = session.execute(text(summary_query))
            summary = summary_result.fetchone()
            
            print(f"📈 Summary:")
            print(f"  - Symbols with MACD: {summary[0]}")
            print(f"  - Total MACD records: {summary[1]}")
            print(f"  - Total symbols with price data: {summary[2]}")
            
    except Exception as e:
        print(f"❌ Fatal error: {e}")
        raise

def calculate_macd_for_specific_symbols(symbols):
    """Calculate MACD for specific symbols only"""
    
    print(f"🔍 Calculating MACD for specific symbols: {', '.join(symbols)}")
    
    try:
        with db.get_session() as session:
            for symbol in symbols:
                print(f"\n📊 Processing {symbol}...")
                
                # Get price data
                price_query = """
                    SELECT date, close
                    FROM raw_market_data_daily 
                    WHERE symbol = :symbol 
                    ORDER BY date ASC
                """
                
                price_result = session.execute(text(price_query), {'symbol': symbol})
                price_rows = price_result.fetchall()
                
                if len(price_rows) < 26:
                    print(f"  ⚠️  Skipping {symbol}: insufficient data ({len(price_rows)} days, need 26+)")
                    continue
                
                # Create DataFrame and calculate MACD
                df = pd.DataFrame(price_rows, columns=['date', 'close'])
                macd_line, macd_signal, macd_hist = calculate_macd(df['close'])
                
                # Update indicators table
                updated_count = 0
                for i, (date, close) in enumerate(price_rows):
                    if (pd.notna(macd_line.iloc[i]) and 
                        pd.notna(macd_signal.iloc[i]) and 
                        pd.notna(macd_hist.iloc[i])):
                        
                        update_query = """
                            UPDATE indicators_daily 
                            SET macd = :macd, 
                                macd_signal = :macd_signal, 
                                macd_hist = :macd_hist,
                                updated_at = NOW()
                            WHERE symbol = :symbol AND date = :date
                        """
                        
                        session.execute(text(update_query), {
                            'macd': float(macd_line.iloc[i]),
                            'macd_signal': float(macd_signal.iloc[j]), 
                            'macd_hist': float(macd_hist.iloc[j]),
                            'symbol': symbol,
                            'date': date
                        })
                        updated_count += 1
                
                session.commit()
                print(f"  ✅ Updated {updated_count} MACD records for {symbol}")
                
    except Exception as e:
        print(f"❌ Error: {e}")
        raise

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Calculate MACD indicators")
    parser.add_argument("--symbols", nargs="+", help="Specific symbols to process (optional)")
    parser.add_argument("--all", action="store_true", help="Process all symbols with missing MACD")
    
    args = parser.parse_args()
    
    if args.symbols:
        calculate_macd_for_specific_symbols(args.symbols)
    elif args.all:
        calculate_missing_macd()
    else:
        print("Usage:")
        print("  python calculate_missing_macd.py --all                    # Process all symbols")
        print("  python calculate_missing_macd.py --symbols CRM HOOD COIN # Specific symbols")
        print("\nDefault: Processing all symbols with missing MACD...")
        calculate_missing_macd()
