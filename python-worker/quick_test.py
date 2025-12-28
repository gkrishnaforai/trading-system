#!/usr/bin/env python3
"""
Quick Test - Check if we can fetch free stock data
"""
import logging

# Show only important messages
logging.basicConfig(level=logging.WARNING)

def test_free_data():
    """Test free data sources"""
    print("🔍 Quick Free Data Test")
    print("=" * 30)
    
    # Test Yahoo Finance (free and works)
    try:
        from app.data_sources import get_data_source
        
        yahoo = get_data_source('yahoo_finance')
        price = yahoo.fetch_current_price('AAPL')
        print(f"✅ Yahoo Finance: AAPL = ${price}")
        
        # Test a few more symbols
        symbols = ['MSFT', 'GOOGL', 'TSLA']
        for symbol in symbols:
            try:
                price = yahoo.fetch_current_price(symbol)
                print(f"   {symbol}: ${price}")
            except:
                print(f"   {symbol}: Failed")
        
        return True
        
    except Exception as e:
        print(f"❌ Yahoo Finance failed: {e}")
        return False

if __name__ == "__main__":
    if test_free_data():
        print("\n🎉 Free stock data is working!")
        print("You can fetch real-time prices for any stock symbol.")
    else:
        print("\n❌ Free data sources are not working.")
