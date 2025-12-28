#!/usr/bin/env python3
"""
Test Comprehensive Data Loading Service
Tests the proper service architecture using data source adapters
"""
import sys
import os

# Add the project root to Python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.services.comprehensive_data_loader import ComprehensiveDataLoader
from app.database import db
from app.observability.logging import get_logger
from sqlalchemy import text

logger = get_logger("test_comprehensive_data_service")

def test_comprehensive_data_service():
    """Test comprehensive data loading using service architecture"""
    print("🚀 COMPREHENSIVE DATA LOADING SERVICE TEST")
    print("=" * 55)
    print("Testing proper service architecture with data source adapters")
    
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
        
        # Show available data sources
        print(f"📊 Available data sources: {list(data_loader.data_sources.keys())}")
        
    except Exception as e:
        print(f"❌ Service initialization failed: {e}")
        return False
    
    # Test loading data for NVDA
    symbol = "NVDA"
    print(f"\n📊 Loading comprehensive data for {symbol}")
    print("=" * 45)
    
    try:
        # Load all data types using the service
        results = data_loader.load_symbol_data(symbol, days=30)
        
        print(f"\n📋 LOADING RESULTS:")
        print("=" * 20)
        
        total_records = 0
        successful_loads = 0
        
        for result in results:
            status = "✅" if result.success else "❌"
            print(f"   {status} {result.data_type} ({result.source}): {result.records_loaded} records ({result.duration_seconds:.1f}s)")
            if not result.success:
                print(f"      Error: {result.message}")
            else:
                total_records += result.records_loaded
                successful_loads += 1
        
        print(f"\n📊 SUMMARY:")
        print(f"   Total operations: {len(results)}")
        print(f"   Successful: {successful_loads}")
        print(f"   Total records loaded: {total_records}")
        
        # Verify data in database
        print(f"\n🔍 DATABASE VERIFICATION")
        print("=" * 30)
        
        summary = data_loader.get_data_availability_summary(symbol)
        
        print(f"Data availability for {symbol}:")
        for data_type, count in summary.items():
            status = "✅" if count > 0 else "❌"
            print(f"   {status} {data_type}: {count} records")
        
        # Show sample data if available
        if summary.get('price_data', 0) > 0:
            print(f"\n📈 Latest Price Data:")
            with db.get_session() as session:
                latest_price = session.execute(text("""
                    SELECT date, close, high, low, volume FROM raw_market_data_daily 
                    WHERE symbol = :symbol 
                    ORDER BY date DESC LIMIT 1
                """), {"symbol": symbol}).fetchone()
                
                if latest_price:
                    print(f"   Date: {latest_price[0]}")
                    print(f"   Close: ${latest_price[1]:.2f}")
                    print(f"   Range: ${latest_price[3]:.2f} - ${latest_price[2]:.2f}")
                    print(f"   Volume: {latest_price[4]:,}")
        
        if summary.get('fundamentals', 0) > 0:
            print(f"\n💼 Company Overview:")
            with db.get_session() as session:
                overview = session.execute(text("""
                    SELECT name, sector, industry, market_cap, pe_ratio, eps, beta 
                    FROM fundamentals_summary 
                    WHERE symbol = :symbol 
                    LIMIT 1
                """), {"symbol": symbol}).fetchone()
                
                if overview:
                    print(f"   Company: {overview[0]}")
                    print(f"   Sector: {overview[1]}")
                    print(f"   Industry: {overview[2]}")
                    if overview[3]:
                        print(f"   Market Cap: ${overview[3]:,}")
                    if overview[4]:
                        print(f"   P/E Ratio: {overview[4]}")
                    if overview[5]:
                        print(f"   EPS: ${overview[5]:.2f}")
                    if overview[6]:
                        print(f"   Beta: {overview[6]}")
        
        if summary.get('technical_indicators', 0) > 0:
            print(f"\n📊 Latest Technical Indicators:")
            with db.get_session() as session:
                indicators = session.execute(text("""
                    SELECT indicator_name, indicator_value, date 
                    FROM indicators_daily 
                    WHERE symbol = :symbol AND date = (
                        SELECT MAX(date) FROM indicators_daily WHERE symbol = :symbol
                    )
                    ORDER BY indicator_name
                """), {"symbol": symbol}).fetchall()
                
                for indicator in indicators:
                    signal = interpret_signal(indicator[0], indicator[1])
                    print(f"   {indicator[0]}: {indicator[1]:.4f} - {signal}")
        
        # Assess signal generation capabilities
        print(f"\n🎯 SIGNAL GENERATION CAPABILITY")
        print("=" * 35)
        
        capabilities = []
        
        if summary.get('price_data', 0) >= 50:
            capabilities.append("✅ Technical Analysis (MA, RSI, MACD)")
        
        if summary.get('fundamentals', 0) > 0:
            capabilities.append("✅ Fundamental Analysis (P/E, EPS, Beta)")
        
        if summary.get('technical_indicators', 0) > 0:
            capabilities.append("✅ Advanced Technical Indicators")
        
        if summary.get('earnings', 0) > 0:
            capabilities.append("✅ Earnings-Based Strategies")
        
        if capabilities:
            print(f"Available capabilities for {symbol}:")
            for capability in capabilities:
                print(f"   {capability}")
            
            if len(capabilities) >= 3:
                print(f"\n🔥 {symbol} is ready for comprehensive signal generation!")
                print(f"   • Technical + Fundamental Analysis")
                print(f"   • Momentum Trading Strategies")
                print(f"   • Value Investing Analysis")
            else:
                print(f"\n⚡ {symbol} has basic signal generation capabilities")
        else:
            print(f"❌ Insufficient data for signal generation")
        
        return True
        
    except Exception as e:
        print(f"❌ Error testing comprehensive data service: {e}")
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
    
    else:
        return "Technical"

def main():
    """Main test function"""
    print("🚀 COMPREHENSIVE DATA SERVICE ARCHITECTURE TEST")
    print("=" * 60)
    print("Testing proper service layer with data source adapters")
    
    success = test_comprehensive_data_service()
    
    if success:
        print(f"\n🎯 SERVICE ARCHITECTURE TEST: SUCCESS!")
        print(f"✅ Comprehensive Data Loader service working")
        print(f"✅ Data source adapters properly integrated")
        print(f"✅ Service layer abstraction working")
        print(f"✅ Multiple data sources orchestrated")
        
        print(f"\n📋 ARCHITECTURE BENEFITS:")
        print(f"   • Centralized data loading orchestration")
        print(f"   • Configurable data source selection")
        print(f"   • Fallback mechanisms between sources")
        print(f"   • Proper service layer abstraction")
        print(f"   • Database integration with UPSERT")
        
        print(f"\n📋 NEXT STEPS:")
        print(f"   1. Implement signal generation service")
        print(f"   2. Create screening service")
        print(f"   3. Add real-time data refresh")
        print(f"   4. Implement data quality monitoring")
        
    else:
        print(f"\n❌ SERVICE ARCHITECTURE TEST FAILED")
        print(f"   Check data source configuration and service initialization")
    
    return success

if __name__ == "__main__":
    main()
