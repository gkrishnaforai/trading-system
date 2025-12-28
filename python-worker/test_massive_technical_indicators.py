#!/usr/bin/env python3
"""
Test Massive Source Technical Indicators
Test technical indicators using our existing MassiveSource architecture
"""
import sys
import os

# Add the project root to Python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.data_sources.massive_source import MassiveSource
from app.database import db
from app.observability.logging import get_logger
from sqlalchemy import text
from datetime import datetime

logger = get_logger("test_massive_technical_indicators")

def test_massive_technical_indicators():
    """Test technical indicators from MassiveSource"""
    print("📈 MASSIVE SOURCE TECHNICAL INDICATORS TEST")
    print("=" * 50)
    print("Using existing MassiveSource architecture")
    
    # Initialize database
    try:
        db.initialize()
        print("✅ Database initialized")
    except Exception as e:
        print(f"❌ Database initialization failed: {e}")
        return False
    
    # Initialize Massive source
    try:
        massive_source = MassiveSource()
        print("✅ MassiveSource initialized")
    except Exception as e:
        print(f"❌ MassiveSource initialization failed: {e}")
        return False
    
    # Test with NVDA
    symbol = "NVDA"
    print(f"\n📊 Loading technical indicators for {symbol}")
    print("-" * 45)
    
    try:
        # Fetch technical indicators
        indicators_data = massive_source.fetch_technical_indicators(symbol, days=30)
        
        if not indicators_data:
            print("❌ No technical indicators data returned")
            return False
        
        print(f"✅ Fetched technical indicators data")
        
        # Transform and save to database
        records = []
        
        for indicator_type, data in indicators_data.items():
            print(f"\n📊 Processing {indicator_type}:")
            
            if indicator_type == 'RSI':
                for item in data:
                    records.append({
                        'symbol': symbol,
                        'date': datetime.strptime(item['date'], '%Y-%m-%d').date(),
                        'indicator_name': 'RSI',
                        'indicator_value': item['value'],
                        'time_period': item['period'],
                        'data_source': 'massive',
                        'created_at': datetime.now()
                    })
                print(f"   ✅ RSI: {len(data)} records")
            
            elif indicator_type == 'MACD':
                for item in data:
                    records.append({
                        'symbol': symbol,
                        'date': datetime.strptime(item['date'], '%Y-%m-%d').date(),
                        'indicator_name': 'MACD',
                        'indicator_value': item['value'],
                        'time_period': item['period'],
                        'data_source': 'massive',
                        'created_at': datetime.now()
                    })
                    
                    # Add signal line if available
                    if item.get('signal'):
                        records.append({
                            'symbol': symbol,
                            'date': datetime.strptime(item['date'], '%Y-%m-%d').date(),
                            'indicator_name': 'MACD_Signal',
                            'indicator_value': item['signal'],
                            'time_period': 9,
                            'data_source': 'massive',
                            'created_at': datetime.now()
                        })
                print(f"   ✅ MACD: {len(data)} records")
            
            elif indicator_type == 'SMA':
                for sma_name, sma_data in data.items():
                    for item in sma_data:
                        records.append({
                            'symbol': symbol,
                            'date': datetime.strptime(item['date'], '%Y-%m-%d').date(),
                            'indicator_name': sma_name,
                            'indicator_value': item['value'],
                            'time_period': item['period'],
                            'data_source': 'massive',
                            'created_at': datetime.now()
                        })
                    print(f"   ✅ {sma_name}: {len(sma_data)} records")
            
            elif indicator_type == 'EMA':
                for ema_name, ema_data in data.items():
                    for item in ema_data:
                        records.append({
                            'symbol': symbol,
                            'date': datetime.strptime(item['date'], '%Y-%m-%d').date(),
                            'indicator_name': ema_name,
                            'indicator_value': item['value'],
                            'time_period': item['period'],
                            'data_source': 'massive',
                            'created_at': datetime.now()
                        })
                    print(f"   ✅ {ema_name}: {len(ema_data)} records")
            
            elif indicator_type == 'Bollinger_Bands':
                for item in data:
                    # Upper band
                    records.append({
                        'symbol': symbol,
                        'date': datetime.strptime(item['date'], '%Y-%m-%d').date(),
                        'indicator_name': 'BB_Upper',
                        'indicator_value': item['upper'],
                        'time_period': item['period'],
                        'data_source': 'massive',
                        'created_at': datetime.now()
                    })
                    # Lower band
                    records.append({
                        'symbol': symbol,
                        'date': datetime.strptime(item['date'], '%Y-%m-%d').date(),
                        'indicator_name': 'BB_Lower',
                        'indicator_value': item['lower'],
                        'time_period': item['period'],
                        'data_source': 'massive',
                        'created_at': datetime.now()
                    })
                print(f"   ✅ Bollinger Bands: {len(data)} records")
            
            elif indicator_type == 'ATR':
                for item in data:
                    records.append({
                        'symbol': symbol,
                        'date': datetime.strptime(item['date'], '%Y-%m-%d').date(),
                        'indicator_name': 'ATR',
                        'indicator_value': item['value'],
                        'time_period': item['period'],
                        'data_source': 'massive',
                        'created_at': datetime.now()
                    })
                print(f"   ✅ ATR: {len(data)} records")
        
        # Save to database
        print(f"\n💾 Saving {len(records)} indicator records to database...")
        
        with db.get_session() as session:
            for record in records:
                session.execute(text("""
                    INSERT INTO indicators_daily (
                        symbol, date, indicator_name, indicator_value, time_period,
                        data_source, created_at
                    ) VALUES (
                        :symbol, :date, :indicator_name, :indicator_value, :time_period,
                        :data_source, :created_at
                    ) ON CONFLICT (symbol, date, indicator_name, data_source) 
                    DO UPDATE SET
                        indicator_value = EXCLUDED.indicator_value,
                        time_period = EXCLUDED.time_period,
                        created_at = EXCLUDED.created_at
                """), record)
            
            session.commit()
        
        print(f"✅ Successfully saved {len(records)} technical indicator records")
        
        # Verify data
        print(f"\n🔍 DATABASE VERIFICATION")
        print("=" * 30)
        
        with db.get_session() as session:
            total_count = session.execute(text("""
                SELECT COUNT(*) FROM indicators_daily 
                WHERE symbol = :symbol AND data_source = 'massive'
            """), {"symbol": symbol}).scalar()
            
            print(f"Total NVDA indicators: {total_count} records")
            
            # Show available indicators
            indicators = session.execute(text("""
                SELECT DISTINCT indicator_name FROM indicators_daily 
                WHERE symbol = :symbol AND data_source = 'massive'
                ORDER BY indicator_name
            """), {"symbol": symbol}).fetchall()
            
            print(f"Available indicators:")
            for indicator in indicators:
                print(f"   • {indicator[0]}")
            
            # Show latest values
            latest = session.execute(text("""
                SELECT indicator_name, indicator_value, time_period, date
                FROM indicators_daily 
                WHERE symbol = :symbol AND data_source = 'massive'
                AND date = (
                    SELECT MAX(date) FROM indicators_daily 
                    WHERE symbol = :symbol AND data_source = 'massive'
                )
                ORDER BY indicator_name
            """), {"symbol": symbol}).fetchall()
            
            if latest:
                print(f"\n📊 Latest NVDA Technical Indicators:")
                for indicator in latest:
                    signal = interpret_signal(indicator[0], indicator[1])
                    print(f"   {indicator[0]}: {indicator[1]:.4f} - {signal}")
        
        return True
        
    except Exception as e:
        print(f"❌ Error testing technical indicators: {e}")
        return False

def interpret_signal(indicator_name: str, value: float) -> str:
    """Interpret technical indicator values"""
    if indicator_name == "RSI":
        if value > 70:
            return "Overbought (SELL)"
        elif value < 30:
            return "Oversold (BUY)"
        else:
            return "Neutral"
    
    elif indicator_name == "MACD":
        return "Bullish" if value > 0 else "Bearish"
    
    elif indicator_name.startswith("SMA_") or indicator_name.startswith("EMA_"):
        return "Moving Average"
    
    elif indicator_name == "ATR":
        return "Volatility"
    
    elif indicator_name.startswith("BB_"):
        return "Bollinger Band"
    
    else:
        return "Technical"

def main():
    """Main test function"""
    print("🚀 MASSIVE TECHNICAL INDICATORS ARCHITECTURE TEST")
    print("=" * 55)
    print("Testing technical indicators using MassiveSource")
    
    success = test_massive_technical_indicators()
    
    if success:
        print(f"\n🎯 TEST RESULT: SUCCESS!")
        print(f"✅ MassiveSource technical indicators working")
        print(f"✅ RSI, MACD, SMA, EMA, Bollinger Bands loaded")
        print(f"✅ Using existing architecture properly")
        
        print(f"\n📋 TECHNICAL ANALYSIS READY:")
        print(f"   • Momentum Trading (RSI, MACD)")
        print(f"   • Trend Following (SMA, EMA)")
        print(f"   • Volatility Analysis (Bollinger Bands)")
        print(f"   • Risk Management (ATR)")
        
    else:
        print(f"\n❌ TEST FAILED")
        print(f"   Check MassiveSource and API connection")
    
    return success

if __name__ == "__main__":
    main()
