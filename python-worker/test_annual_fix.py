#!/usr/bin/env python3
"""
Test the fixed FMP client with annual periods
"""
import sys
import os

# Add the app directory to the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def test_annual_periods():
    """Test the enhanced FMP client with annual periods"""
    print("🔧 TESTING FMP WITH ANNUAL PERIODS")
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
        print("✅ Enhanced client created with annual defaults")
        
        # Test 1: Key Metrics with annual (should work)
        print("\n1️⃣ Testing Key Metrics (Annual)...")
        try:
            metrics = client.get_key_metrics("AAPL", "annual")
            if metrics:
                print(f"   ✅ SUCCESS: {len(metrics)} records")
                if metrics:
                    print(f"   ✅ Latest Market Cap: ${metrics[0]['marketCap']:,}")
                    print(f"   ✅ Latest P/E Ratio: {metrics[0].get('priceEarningsRatio', 'N/A')}")
                    print(f"   ✅ Period: {metrics[0].get('period', 'N/A')}")
            else:
                print(f"   ❌ FAILED: No data returned")
        except Exception as e:
            print(f"   ❌ ERROR: {e}")
        
        # Test 2: Financial Ratios with annual (should work)
        print("\n2️⃣ Testing Financial Ratios (Annual)...")
        try:
            ratios = client.get_financial_ratios("AAPL", "annual")
            if ratios:
                print(f"   ✅ SUCCESS: {len(ratios)} records")
                if ratios:
                    print(f"   ✅ Latest Current Ratio: {ratios[0].get('currentRatio', 'N/A')}")
                    print(f"   ✅ Latest Debt/Equity: {ratios[0].get('debtToEquity', 'N/A')}")
                    print(f"   ✅ Period: {ratios[0].get('period', 'N/A')}")
            else:
                print(f"   ❌ FAILED: No data returned")
        except Exception as e:
            print(f"   ❌ ERROR: {e}")
        
        # Test 3: Key Metrics with quarterly (should fail)
        print("\n3️⃣ Testing Key Metrics (Quarterly - should fail)...")
        try:
            metrics = client.get_key_metrics("AAPL", "quarter")
            if metrics:
                print(f"   ✅ UNEXPECTED SUCCESS: {len(metrics)} records")
            else:
                print(f"   ❌ EXPECTED FAILURE: No data returned (quarterly not supported)")
        except Exception as e:
            print(f"   ❌ EXPECTED ERROR: {e}")
        
        # Test 4: Financial Ratios with quarterly (should fail)
        print("\n4️⃣ Testing Financial Ratios (Quarterly - should fail)...")
        try:
            ratios = client.get_financial_ratios("AAPL", "quarter")
            if ratios:
                print(f"   ✅ UNEXPECTED SUCCESS: {len(ratios)} records")
            else:
                print(f"   ❌ EXPECTED FAILURE: No data returned (quarterly not supported)")
        except Exception as e:
            print(f"   ❌ EXPECTED ERROR: {e}")
        
        print("\n🎉 ANNUAL PERIOD TEST COMPLETE")
        
    except ImportError as e:
        print(f"❌ IMPORT ERROR: {e}")
        print("Make sure all dependencies are installed")
    except Exception as e:
        print(f"❌ SETUP ERROR: {e}")


def test_optimized_loader_annual():
    """Test the optimized loader with annual periods"""
    print("\n🚀 TESTING OPTIMIZED LOADER (ANNUAL)")
    print("=" * 50)
    
    try:
        from app.services.optimized_fmp_loader import optimized_fmp_loader
        
        # Test key metrics (should default to annual)
        print("\n1️⃣ Testing Key Metrics (Default Annual)...")
        metrics = optimized_fmp_loader.get_key_metrics("AAPL")
        if metrics:
            print(f"   ✅ SUCCESS: {len(metrics)} records")
            if metrics:
                print(f"   ✅ Latest Market Cap: ${metrics[0]['marketCap']:,}")
        else:
            print(f"   ❌ FAILED: No data returned")
        
        # Test financial ratios (should default to annual)
        print("\n2️⃣ Testing Financial Ratios (Default Annual)...")
        ratios = optimized_fmp_loader.get_financial_ratios("AAPL")
        if ratios:
            print(f"   ✅ SUCCESS: {len(ratios)} records")
            if ratios:
                print(f"   ✅ Latest Current Ratio: {ratios[0].get('currentRatio', 'N/A')}")
        else:
            print(f"   ❌ FAILED: No data returned")
        
        # Test explicit annual
        print("\n3️⃣ Testing Explicit Annual...")
        metrics_annual = optimized_fmp_loader.get_key_metrics("AAPL", "annual")
        if metrics_annual:
            print(f"   ✅ SUCCESS: {len(metrics_annual)} records")
        else:
            print(f"   ❌ FAILED: No data returned")
        
        print("\n🎉 OPTIMIZED LOADER TEST COMPLETE")
        
    except Exception as e:
        print(f"❌ OPTIMIZED LOADER ERROR: {e}")


def main():
    """Main test function"""
    print("🔧 TESTING ANNUAL PERIOD FIX")
    print("=" * 60)
    print("This test verifies that annual periods work and quarterly fails as expected")
    print("=" * 60)
    
    # Test the enhanced client
    test_annual_periods()
    
    # Test the optimized loader
    test_optimized_loader_annual()
    
    print("\n" + "=" * 60)
    print("🎯 ANNUAL FIX TEST COMPLETE")
    print("=" * 60)
    print("If annual works and quarterly fails, the fix is successful!")


if __name__ == "__main__":
    main()
