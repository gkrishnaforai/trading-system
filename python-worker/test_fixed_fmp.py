#!/usr/bin/env python3
"""
Test the fixed FMP client with curl-like headers
"""
import sys
import os

# Add the app directory to the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def test_fixed_client():
    """Test the fixed enhanced FMP client"""
    print("🔧 TESTING FIXED FMP CLIENT")
    print("=" * 50)
    
    try:
        from app.providers.financial_modeling_prep.client import EnhancedFMPClient, FinancialModelingPrepConfig
        
        # Create config with your API key
        config = FinancialModelingPrepConfig(
            api_key="4Bva21oWNpNCRLXQ6vqhvN0jfk38QzXQ",
            base_url="https://financialmodelingprep.com/stable",
            timeout=30,
            max_retries=3,
            retry_delay=1.0,
            rate_limit_calls=60,
            rate_limit_window=60.0
        )
        
        # Create client
        client = EnhancedFMPClient(config)
        print("✅ Enhanced client created with curl-like headers")
        
        # Test 1: Quote (should work)
        print("\n1️⃣ Testing Quote...")
        try:
            quote = client.get_real_time_quote("AAPL")
            if quote:
                print(f"   ✅ SUCCESS: AAPL Price: ${quote['price']}")
            else:
                print(f"   ❌ FAILED: No data returned")
        except Exception as e:
            print(f"   ❌ ERROR: {e}")
        
        # Test 2: Key Metrics (should now work)
        print("\n2️⃣ Testing Key Metrics...")
        try:
            metrics = client.get_key_metrics("AAPL", "quarter")
            if metrics:
                print(f"   ✅ SUCCESS: {len(metrics)} records")
                if metrics:
                    print(f"   ✅ Latest Market Cap: ${metrics[0]['marketCap']:,}")
                    print(f"   ✅ Latest P/E Ratio: {metrics[0].get('priceEarningsRatio', 'N/A')}")
            else:
                print(f"   ❌ FAILED: No data returned")
        except Exception as e:
            print(f"   ❌ ERROR: {e}")
        
        # Test 3: Financial Ratios (should now work)
        print("\n3️⃣ Testing Financial Ratios...")
        try:
            ratios = client.get_financial_ratios("AAPL", "quarter")
            if ratios:
                print(f"   ✅ SUCCESS: {len(ratios)} records")
                if ratios:
                    print(f"   ✅ Latest Current Ratio: {ratios[0].get('currentRatio', 'N/A')}")
                    print(f"   ✅ Latest Debt/Equity: {ratios[0].get('debtToEquity', 'N/A')}")
            else:
                print(f"   ❌ FAILED: No data returned")
        except Exception as e:
            print(f"   ❌ ERROR: {e}")
        
        # Test 4: Company Profile (should work)
        print("\n4️⃣ Testing Company Profile...")
        try:
            profile = client.get_company_profile("AAPL")
            if profile:
                print(f"   ✅ SUCCESS: {profile['companyName']}")
                print(f"   ✅ Sector: {profile.get('sector', 'N/A')}")
                print(f"   ✅ Market Cap: ${profile.get('marketCap', 0):,}")
            else:
                print(f"   ❌ FAILED: No data returned")
        except Exception as e:
            print(f"   ❌ ERROR: {e}")
        
        # Test 5: Income Statement (should work)
        print("\n5️⃣ Testing Income Statement...")
        try:
            income = client.get_income_statement("AAPL", "quarter")
            if income:
                print(f"   ✅ SUCCESS: {len(income)} records")
                if income:
                    print(f"   ✅ Latest Revenue: ${income[0].get('revenue', 0):,}")
                    print(f"   ✅ Latest Net Income: ${income[0].get('netIncome', 0):,}")
            else:
                print(f"   ❌ FAILED: No data returned")
        except Exception as e:
            print(f"   ❌ ERROR: {e}")
        
        print("\n🎉 TEST COMPLETE")
        print("If all tests pass, the enhanced client is working!")
        
    except ImportError as e:
        print(f"❌ IMPORT ERROR: {e}")
        print("Make sure all dependencies are installed")
    except Exception as e:
        print(f"❌ SETUP ERROR: {e}")


def test_optimized_loader():
    """Test the optimized loader with fixed client"""
    print("\n🚀 TESTING OPTIMIZED LOADER")
    print("=" * 50)
    
    try:
        from app.services.optimized_fmp_loader import optimized_fmp_loader
        
        # Test real-time price
        print("\n1️⃣ Testing Real-time Price...")
        price = optimized_fmp_loader.get_real_time_price("AAPL")
        if price:
            print(f"   ✅ SUCCESS: AAPL Price: ${price['price']}")
        else:
            print(f"   ❌ FAILED: No data returned")
        
        # Test key metrics
        print("\n2️⃣ Testing Key Metrics...")
        metrics = optimized_fmp_loader.get_key_metrics("AAPL", "quarter")
        if metrics:
            print(f"   ✅ SUCCESS: {len(metrics)} records")
        else:
            print(f"   ❌ FAILED: No data returned")
        
        # Test financial ratios
        print("\n3️⃣ Testing Financial Ratios...")
        ratios = optimized_fmp_loader.get_financial_ratios("AAPL", "quarter")
        if ratios:
            print(f"   ✅ SUCCESS: {len(ratios)} records")
        else:
            print(f"   ❌ FAILED: No data returned")
        
        # Test comprehensive data
        print("\n4️⃣ Testing Comprehensive Data...")
        comprehensive = optimized_fmp_loader.get_financials("AAPL")
        if comprehensive:
            print(f"   ✅ SUCCESS: Comprehensive data available")
            print(f"   ✅ Data types: {list(comprehensive.keys())}")
        else:
            print(f"   ❌ FAILED: No data returned")
        
        print("\n🎉 OPTIMIZED LOADER TEST COMPLETE")
        
    except Exception as e:
        print(f"❌ OPTIMIZED LOADER ERROR: {e}")


def main():
    """Main test function"""
    print("🔧 TESTING FIXED FMP INTEGRATION")
    print("=" * 60)
    print("This test verifies the enhanced FMP client works with curl-like headers")
    print("=" * 60)
    
    # Test the fixed client
    test_fixed_client()
    
    # Test the optimized loader
    test_optimized_loader()
    
    print("\n" + "=" * 60)
    print("🎯 ALL TESTS COMPLETE")
    print("=" * 60)
    print("If everything works, the FMP integration is ready!")


if __name__ == "__main__":
    main()
