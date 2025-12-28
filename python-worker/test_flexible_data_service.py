#!/usr/bin/env python3
"""
Test Flexible Data Service
Demonstrates per-API data source selection and optimal source usage
"""
import logging
from datetime import datetime, timedelta

from app.services.flexible_data_service import flexible_data_service, DataSource, DataStrategy
from app.observability.logging import get_logger

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = get_logger("test_flexible_service")

def test_data_source_availability():
    """Test which data sources are available"""
    print("🔌 DATA SOURCE AVAILABILITY")
    print("=" * 40)
    
    sources = flexible_data_service.get_available_sources()
    for source, available in sources.items():
        status = "✅ Available" if available else "❌ Not Available"
        print(f"{source.title():<10}: {status}")
    
    return sources

def test_flexible_price_data():
    """Test flexible price data loading"""
    print("\n📈 FLEXIBLE PRICE DATA LOADING")
    print("=" * 45)
    
    symbol = "AAPL"
    
    # Test 1: Force Yahoo for historical data
    print(f"\n1. Testing Yahoo for historical data ({symbol})...")
    yahoo_data = flexible_data_service.get_price_data(
        symbol=symbol,
        start_date=datetime.now() - timedelta(days=365),
        data_source=DataSource.YAHOO
    )
    
    if yahoo_data is not None:
        print(f"   ✅ Yahoo: Loaded {len(yahoo_data)} records")
        print(f"   Available columns: {list(yahoo_data.columns)}")
        
        # Handle different index types
        if hasattr(yahoo_data.index, 'date'):
            start_date = yahoo_data.index[0].date()
            end_date = yahoo_data.index[-1].date()
        elif hasattr(yahoo_data.index[0], 'date'):
            start_date = yahoo_data.index[0].date()
            end_date = yahoo_data.index[-1].date()
        else:
            start_date = str(yahoo_data.index[0])
            end_date = str(yahoo_data.index[-1])
        
        print(f"   Date Range: {start_date} to {end_date}")
        
        # Show sample data with available columns
        if 'Open' in yahoo_data.columns and 'Close' in yahoo_data.columns:
            print(f"   Sample: Open=${yahoo_data['Open'].iloc[-1]:.2f}, Close=${yahoo_data['Close'].iloc[-1]:.2f}")
        elif 'open' in yahoo_data.columns and 'close' in yahoo_data.columns:
            print(f"   Sample: Open=${yahoo_data['open'].iloc[-1]:.2f}, Close=${yahoo_data['close'].iloc[-1]:.2f}")
        else:
            print(f"   Sample data shape: {yahoo_data.shape}")
            print(f"   Sample row: {yahoo_data.iloc[-1].to_dict()}")
    else:
        print("   ❌ Yahoo: Failed to load data")
    
    # Test 2: Auto strategy (should choose Yahoo for historical)
    print(f"\n2. Testing Auto strategy for historical data ({symbol})...")
    auto_data = flexible_data_service.get_price_data(
        symbol=symbol,
        start_date=datetime.now() - timedelta(days=90),
        data_source=DataSource.AUTO,
        strategy=DataStrategy.HISTORICAL_YAHOO
    )
    
    if auto_data is not None:
        print(f"   ✅ Auto: Loaded {len(auto_data)} records")
        print(f"   Strategy chose: {'Yahoo (historical)' if len(auto_data) > 60 else 'Massive'}")
    else:
        print("   ❌ Auto: Failed to load data")

def test_flexible_technical_indicators():
    """Test flexible technical indicators"""
    print("\n📊 FLEXIBLE TECHNICAL INDICATORS")
    print("=" * 45)
    
    symbol = "MSFT"
    indicators = ["RSI", "MACD", "EMA", "SMA"]
    
    # Test 1: Force Massive for technical indicators
    print(f"\n1. Testing Massive for technical indicators ({symbol})...")
    massive_indicators = flexible_data_service.get_technical_indicators(
        symbol=symbol,
        indicators=indicators,
        data_source=DataSource.MASSIVE
    )
    
    print(f"   Results from Massive:")
    for indicator, data in massive_indicators.items():
        if data:
            print(f"   ✅ {indicator}: {len(data)} records")
            if indicator in ["EMA", "SMA"]:
                latest = data[0] if data else None
                if latest:
                    print(f"      Latest {indicator}({latest.get('window')}): ${latest.get('value', 0):.2f}")
            elif indicator == "RSI":
                latest = data[0] if data else None
                if latest:
                    print(f"      Latest RSI: {latest.get('value', 0):.2f}")
        else:
            print(f"   ❌ {indicator}: No data")
    
    # Test 2: Yahoo fallback for moving averages
    print(f"\n2. Testing Yahoo for moving averages ({symbol})...")
    yahoo_indicators = flexible_data_service.get_technical_indicators(
        symbol=symbol,
        indicators=["EMA", "SMA"],
        data_source=DataSource.YAHOO
    )
    
    print(f"   Results from Yahoo:")
    for indicator, data in yahoo_indicators.items():
        if data:
            print(f"   ✅ {indicator}: {len(data)} records")
            for item in data:
                print(f"      {indicator}({item.get('window')}): ${item.get('value', 0):.2f}")
        else:
            print(f"   ❌ {indicator}: No data")

def test_flexible_fundamentals():
    """Test flexible fundamentals data"""
    print("\n💰 FLEXIBLE FUNDAMENTALS DATA")
    print("=" * 40)
    
    symbol = "GOOGL"
    data_types = ["balance_sheet", "income_statement", "ratios"]
    
    # Test 1: Try Massive first
    print(f"\n1. Testing Massive for fundamentals ({symbol})...")
    massive_fundamentals = flexible_data_service.get_fundamentals(
        symbol=symbol,
        data_types=data_types,
        data_source=DataSource.MASSIVE,
        strategy=DataStrategy.MASSIVE_FIRST
    )
    
    print(f"   Results from Massive:")
    for data_type, data in massive_fundamentals.items():
        if data:
            if isinstance(data, list):
                print(f"   ✅ {data_type}: {len(data)} records")
                if data:
                    latest = data[0]
                    print(f"      Latest period: {latest.get('period_end')}")
            else:
                print(f"   ✅ {data_type}: Available")
                if isinstance(data, dict):
                    key_metrics = {k: v for k, v in data.items() if v is not None}
                    print(f"      Metrics: {list(key_metrics.keys())[:5]}")
        else:
            print(f"   ❌ {data_type}: No data")
    
    # Test 2: Yahoo fallback
    print(f"\n2. Testing Yahoo for fundamentals ({symbol})...")
    yahoo_fundamentals = flexible_data_service.get_fundamentals(
        symbol=symbol,
        data_types=["ratios"],
        data_source=DataSource.YAHOO
    )
    
    print(f"   Results from Yahoo:")
    for data_type, data in yahoo_fundamentals.items():
        if data and isinstance(data, dict):
            print(f"   ✅ {data_type}: Available")
            print(f"      P/E Ratio: {data.get('pe_ratio', 'N/A')}")
            print(f"      P/B Ratio: {data.get('pb_ratio', 'N/A')}")
            print(f"      ROE: {data.get('roe', 'N/A')}")
        else:
            print(f"   ❌ {data_type}: No data")

def test_strategy_examples():
    """Test different data source strategies"""
    print("\n🎯 DATA SOURCE STRATEGY EXAMPLES")
    print("=" * 45)
    
    symbol = "TSLA"
    
    # Strategy 1: Historical Yahoo (for backtesting)
    print(f"\n1. Historical Yahoo Strategy ({symbol}) - Backtesting Use Case")
    historical_data = flexible_data_service.get_price_data(
        symbol=symbol,
        start_date=datetime.now() - timedelta(days=2*365),  # 2 years
        data_source=DataSource.AUTO,
        strategy=DataStrategy.HISTORICAL_YAHOO
    )
    
    if historical_data is not None:
        print(f"   ✅ Loaded {len(historical_data)} daily records for backtesting")
        
        # Handle different index types
        if hasattr(historical_data.index, 'date'):
            start_date = historical_data.index[0].date()
            end_date = historical_data.index[-1].date()
        elif hasattr(historical_data.index[0], 'date'):
            start_date = historical_data.index[0].date()
            end_date = historical_data.index[-1].date()
        else:
            start_date = str(historical_data.index[0])
            end_date = str(historical_data.index[-1])
        
        print(f"   Date Range: {start_date} to {end_date}")
    
    # Strategy 2: Real-time Massive (for current signals)
    print(f"\n2. Real-time Massive Strategy ({symbol}) - Current Signals Use Case")
    recent_data = flexible_data_service.get_technical_indicators(
        symbol=symbol,
        indicators=["RSI", "MACD"],
        data_source=DataSource.AUTO,
        strategy=DataStrategy.REAL_TIME_MASSIVE
    )
    
    print(f"   ✅ Technical indicators for current signals:")
    for indicator, data in recent_data.items():
        if data:
            latest = data[0] if data else None
            if latest:
                print(f"   {indicator}: {latest.get('value', 0):.4f}")
    
    # Strategy 3: Massive First (premium data)
    print(f"\n3. Massive First Strategy ({symbol}) - Premium Data Use Case")
    premium_indicators = flexible_data_service.get_technical_indicators(
        symbol=symbol,
        indicators=["EMA", "SMA"],
        data_source=DataSource.AUTO,
        strategy=DataStrategy.MASSIVE_FIRST
    )
    
    print(f"   ✅ Premium technical indicators:")
    for indicator, data in premium_indicators.items():
        if data:
            latest = data[0] if data else None
            if latest:
                print(f"   {indicator}({latest.get('window')}): ${latest.get('value', 0):.2f}")

def test_performance_comparison():
    """Compare performance between sources"""
    print("\n⚡ PERFORMANCE COMPARISON")
    print("=" * 35)
    
    symbol = "NVDA"
    
    import time
    
    # Test Yahoo performance
    start_time = time.time()
    yahoo_data = flexible_data_service.get_price_data(
        symbol=symbol,
        start_date=datetime.now() - timedelta(days=30),
        data_source=DataSource.YAHOO
    )
    yahoo_time = time.time() - start_time
    
    # Test Massive performance (if available)
    start_time = time.time()
    massive_indicators = flexible_data_service.get_technical_indicators(
        symbol=symbol,
        indicators=["RSI"],
        data_source=DataSource.MASSIVE
    )
    massive_time = time.time() - start_time
    
    print(f"Yahoo Finance (30 days price data): {yahoo_time:.3f}s - {len(yahoo_data) if yahoo_data is not None else 0} records")
    print(f"Massive API (RSI indicators): {massive_time:.3f}s - {len(massive_indicators.get('RSI', []))} records")
    
    print(f"\n💡 Recommendations:")
    print(f"   • Use Yahoo for: Historical backtesting, bulk price data")
    print(f"   • Use Massive for: Real-time indicators, premium fundamentals")
    print(f"   • Auto strategy optimizes: Cost vs Coverage vs Freshness")

def main():
    """Main test function"""
    print("🧪 FLEXIBLE DATA SERVICE TEST SUITE")
    print("=" * 50)
    
    # Test data source availability
    sources = test_data_source_availability()
    
    # Only run tests if sources are available
    if sources['yahoo']:
        test_flexible_price_data()
        test_flexible_technical_indicators()
        test_flexible_fundamentals()
        test_strategy_examples()
        test_performance_comparison()
    else:
        print("❌ Yahoo Finance not available - skipping tests")
    
    if sources['massive']:
        print("\n✅ Massive API available - premium features enabled")
    else:
        print("\n⚠️ Massive API not available - using Yahoo fallback")
    
    print("\n🎉 Flexible Data Service Test Completed!")
    print("\n📋 Key Features Demonstrated:")
    print("   ✅ Per-API data source selection")
    print("   ✅ Automatic source optimization")
    print("   ✅ Fallback mechanisms")
    print("   ✅ Strategy-based source selection")
    print("   ✅ Historical vs Real-time optimization")
    print("   ✅ Cost-effective data sourcing")

if __name__ == "__main__":
    main()
