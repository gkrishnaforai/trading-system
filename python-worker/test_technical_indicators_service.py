#!/usr/bin/env python3
"""
Test Technical Indicators Service
Focused test for loading technical indicators using Massive adapter
"""
import sys
import os

# Add the project root to Python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.services.comprehensive_data_loader import ComprehensiveDataLoader
from app.database import db
from app.observability.logging import get_logger
from sqlalchemy import text
from datetime import datetime

logger = get_logger("test_technical_indicators_service")

def test_technical_indicators_loading():
    """Test technical indicators loading using service architecture"""
    print("📈 TECHNICAL INDICATORS SERVICE TEST")
    print("=" * 45)
    print("Testing technical indicators loading via service layer")
    
    # Initialize database
    try:
        db.initialize()
        print("✅ Database initialized")
    except Exception as e:
        print(f"❌ Database initialization failed: {e}")
        return False
    
    # Initialize comprehensive data loader service
    try:
        data_loader = ComprehensiveDataLoader()
        print("✅ Comprehensive Data Loader service initialized")
        
        # Check available data sources
        print(f"📊 Available data sources: {list(data_loader.data_sources.keys())}")
        
        if 'massive' not in data_loader.data_sources:
            print("❌ Massive data source not available")
            return False
        
        print("✅ Massive data source available")
        
    except Exception as e:
        print(f"❌ Service initialization failed: {e}")
        return False
    
    # Test loading technical indicators for NVDA
    symbol = "NVDA"
    print(f"\n📊 Loading technical indicators for {symbol}")
    print("=" * 45)
    
    try:
        # Test the Massive adapter directly first
        print("🔍 Testing Massive adapter directly...")
        massive_adapter = data_loader.data_sources['massive']
        
        # Fetch technical indicators
        indicators_data = massive_adapter.fetch_technical_indicators(symbol, days=30)
        
        if not indicators_data:
            print("❌ No technical indicators data returned from Massive")
            return False
        
        print(f"✅ Fetched technical indicators from Massive:")
        for indicator_type, data in indicators_data.items():
            if isinstance(data, list):
                print(f"   • {indicator_type}: {len(data)} records")
            elif isinstance(data, dict):
                if indicator_type == 'SMA':
                    for sma_name, sma_data in data.items():
                        print(f"   • {sma_name}: {len(sma_data)} records")
                elif indicator_type == 'EMA':
                    for ema_name, ema_data in data.items():
                        print(f"   • {ema_name}: {len(ema_data)} records")
                else:
                    print(f"   • {indicator_type}: {len(data)} records")
        
        # Save to database using the service method
        print(f"\n💾 Saving technical indicators to database...")
        records_loaded = data_loader._save_technical_indicators(indicators_data, symbol)
        
        if records_loaded > 0:
            print(f"✅ Successfully saved {records_loaded} technical indicator records")
        else:
            print("❌ No records saved to database")
            return False
        
        # Verify data in database
        print(f"\n🔍 DATABASE VERIFICATION")
        print("=" * 30)
        
        with db.get_session() as session:
            # Total indicators count
            total_count = session.execute(text("""
                SELECT COUNT(*) FROM indicators_daily 
                WHERE stock_symbol = :symbol AND data_source = 'massive'
            """), {"symbol": symbol}).scalar()
            
            print(f"Total NVDA indicators (Massive): {total_count} records")
            
            # Available indicator types
            indicator_types = session.execute(text("""
                SELECT DISTINCT indicator_name FROM indicators_daily 
                WHERE stock_symbol = :symbol AND data_source = 'massive'
                ORDER BY indicator_name
            """), {"symbol": symbol}).fetchall()
            
            print(f"Available indicators:")
            for indicator in indicator_types:
                count = session.execute(text("""
                    SELECT COUNT(*) FROM indicators_daily 
                    WHERE stock_symbol = :symbol AND indicator_name = :indicator_name AND data_source = 'massive'
                """), {"symbol": symbol, "indicator_name": indicator[0]}).scalar()
                print(f"   • {indicator[0]}: {count} records")
            
            # Latest values
            latest = session.execute(text("""
                SELECT indicator_name, indicator_value, time_period, trade_date
                FROM indicators_daily 
                WHERE stock_symbol = :symbol AND data_source = 'massive'
                AND trade_date = (
                    SELECT MAX(trade_date) FROM indicators_daily 
                    WHERE stock_symbol = :symbol AND data_source = 'massive'
                )
                ORDER BY indicator_name
            """), {"symbol": symbol}).fetchall()
            
            if latest:
                print(f"\n📊 Latest NVDA Technical Indicators:")
                for indicator in latest:
                    signal = interpret_signal(indicator[0], indicator[1])
                    print(f"   {indicator[0]}: {indicator[1]:.4f} (period: {indicator[2]}) - {signal}")
        
        return True
        
    except Exception as e:
        print(f"❌ Error testing technical indicators: {e}")
        import traceback
        traceback.print_exc()
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
    print("🚀 TECHNICAL INDICATORS SERVICE ARCHITECTURE TEST")
    print("=" * 55)
    print("Testing technical indicators via service layer")
    
    success = test_technical_indicators_loading()
    
    if success:
        print(f"\n🎯 TECHNICAL INDICATORS TEST: SUCCESS!")
        print(f"✅ Service architecture working properly")
        print(f"✅ Massive adapter integrated")
        print(f"✅ Technical indicators loaded and saved")
        print(f"✅ Database integration working")
        
        print(f"\n📋 TECHNICAL ANALYSIS CAPABILITIES:")
        print(f"   • Momentum Trading (RSI, MACD)")
        print(f"   • Trend Following (SMA, EMA)")
        print(f"   • Volatility Analysis (Bollinger Bands, ATR)")
        print(f"   • Multi-timeframe analysis")
        
        print(f"\n📋 NEXT STEPS:")
        print(f"   1. Test price data loading")
        print(f"   2. Implement signal generation service")
        print(f"   3. Create screening strategies")
        
    else:
        print(f"\n❌ TECHNICAL INDICATORS TEST FAILED")
        print(f"   Check Massive API connection and adapter configuration")
    
    return success

if __name__ == "__main__":
    main()
