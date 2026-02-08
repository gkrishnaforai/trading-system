#!/usr/bin/env python3
"""
Test earnings transcript fix for current year only
"""
import sys
import os
from datetime import datetime

# Add the app directory to the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def test_current_year_earnings():
    """Test current year earnings transcript functionality"""
    print("📞 TESTING CURRENT YEAR EARNINGS TRANSCRIPTS")
    print("=" * 60)
    
    current_year = datetime.now().year
    print(f"📅 Current Year: {current_year}")
    
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
        print("✅ Enhanced client created")
        
        # Test 1: Earnings transcript with current year (should work)
        print(f"\n1️⃣ Testing Earnings Transcript (Current Year: {current_year})...")
        try:
            transcript = client.get_earning_transcript("AAPL", year=current_year)
            if transcript:
                print(f"   ✅ SUCCESS: {len(transcript)} transcript(s)")
                for i, item in enumerate(transcript[:2]):
                    print(f"   📞 {i+1}. Symbol: {item.get('symbol', 'N/A')}")
                    print(f"      📅 Year: {item.get('year', 'N/A')}")
                    print(f"      📊 Quarter: {item.get('quarter', 'N/A')}")
                    print(f"      📝 Content length: {len(str(item.get('content', '')))}")
                    print()
            else:
                print(f"   ❌ No transcripts found for current year")
        except Exception as e:
            print(f"   ❌ ERROR: {e}")
        
        # Test 2: Earnings transcript with specific quarter (should work)
        print(f"\n2️⃣ Testing Earnings Transcript (Current Year Q3)...")
        try:
            transcript_q3 = client.get_earning_transcript("AAPL", year=current_year, quarter=3)
            if transcript_q3:
                print(f"   ✅ SUCCESS: {len(transcript_q3)} transcript(s)")
                if transcript_q3:
                    item = transcript_q3[0]
                    print(f"   📞 Symbol: {item.get('symbol', 'N/A')}")
                    print(f"   📅 Year: {item.get('year', 'N/A')}")
                    print(f"   📊 Quarter: {item.get('quarter', 'N/A')}")
            else:
                print(f"   ❌ No Q3 transcript found for current year")
        except Exception as e:
            print(f"   ❌ ERROR: {e}")
        
        # Test 3: Earnings transcript with old year (should default to current)
        print(f"\n3️⃣ Testing Earnings Transcript (Old Year 2020 - should default to current)...")
        try:
            transcript_old = client.get_earning_transcript("AAPL", year=2020)
            if transcript_old:
                print(f"   ✅ SUCCESS: {len(transcript_old)} transcript(s)")
                if transcript_old:
                    item = transcript_old[0]
                    actual_year = item.get('year', 'N/A')
                    print(f"   📞 Requested Year: 2020")
                    print(f"   📅 Actual Year: {actual_year}")
                    if actual_year == current_year:
                        print(f"   ✅ Correctly defaulted to current year")
                    else:
                        print(f"   ⚠️  Did not default to current year")
            else:
                print(f"   ❌ No transcripts found")
        except Exception as e:
            print(f"   ❌ ERROR: {e}")
        
        # Test 4: Get transcript dates (should work)
        print(f"\n4️⃣ Testing Transcript Dates...")
        try:
            dates = client.get_transcript_dates_by_symbol("AAPL")
            if dates:
                print(f"   ✅ SUCCESS: {len(dates)} transcript dates available")
                for i, date_info in enumerate(dates[:3]):
                    print(f"   📅 {i+1}. Date: {date_info.get('date', 'N/A')}")
                    print(f"      📊 Quarter: {date_info.get('quarter', 'N/A')}")
                    print(f"      📅 Year: {date_info.get('year', 'N/A')}")
                    print()
            else:
                print(f"   ❌ No transcript dates found")
        except Exception as e:
            print(f"   ❌ ERROR: {e}")
        
        # Test 5: Latest earnings transcripts (should work)
        print(f"\n5️⃣ Testing Latest Earnings Transcripts...")
        try:
            latest = client.get_latest_earning_transcripts()
            if latest:
                print(f"   ✅ SUCCESS: {len(latest)} latest transcripts")
                for i, item in enumerate(latest[:2]):
                    print(f"   📞 {i+1}. Symbol: {item.get('symbol', 'N/A')}")
                    print(f"      📅 Date: {item.get('date', 'N/A')}")
                    print(f"      📊 Quarter: {item.get('quarter', 'N/A')}")
                    print()
            else:
                print(f"   ❌ No latest transcripts found")
        except Exception as e:
            print(f"   ❌ ERROR: {e}")
        
        print("\n🎉 CURRENT YEAR EARNINGS TEST COMPLETE")
        
    except ImportError as e:
        print(f"❌ IMPORT ERROR: {e}")
        print("Make sure all dependencies are installed")
    except Exception as e:
        print(f"❌ SETUP ERROR: {e}")


def test_optimized_loader_earnings():
    """Test optimized loader earnings functionality"""
    print("\n🚀 TESTING OPTIMIZED LOADER EARNINGS")
    print("=" * 60)
    
    try:
        from app.services.optimized_fmp_loader import optimized_fmp_loader
        
        # Test earnings transcript (should default to current year)
        print("\n1️⃣ Testing Earnings Transcript (Default Current Year)...")
        transcript = optimized_fmp_loader.get_earnings_transcript("AAPL")
        if transcript:
            print(f"   ✅ SUCCESS: {len(transcript)} transcript(s)")
            if transcript:
                item = transcript[0]
                print(f"   📞 Symbol: {item.get('symbol', 'N/A')}")
                print(f"   📅 Year: {item.get('year', 'N/A')}")
        else:
            print(f"   ❌ No transcript found")
        
        # Test earnings transcript with explicit current year
        current_year = datetime.now().year
        print(f"\n2️⃣ Testing Earnings Transcript (Explicit {current_year})...")
        transcript_explicit = optimized_fmp_loader.get_earnings_transcript("AAPL", year=current_year)
        if transcript_explicit:
            print(f"   ✅ SUCCESS: {len(transcript_explicit)} transcript(s)")
        else:
            print(f"   ❌ No transcript found")
        
        # Test earnings transcript with quarter
        print(f"\n3️⃣ Testing Earnings Transcript (Q3)...")
        transcript_q3 = optimized_fmp_loader.get_earnings_transcript("AAPL", quarter=3)
        if transcript_q3:
            print(f"   ✅ SUCCESS: {len(transcript_q3)} transcript(s)")
        else:
            print(f"   ❌ No Q3 transcript found")
        
        print("\n🎉 OPTIMIZED LOADER EARNINGS TEST COMPLETE")
        
    except Exception as e:
        print(f"❌ OPTIMIZED LOADER ERROR: {e}")


def main():
    """Main test function"""
    print("📞 TESTING CURRENT YEAR EARNINGS FIX")
    print("=" * 60)
    print("This test verifies that earnings transcripts are limited to current year")
    print("=" * 60)
    
    # Test current year earnings
    test_current_year_earnings()
    
    # Test optimized loader earnings
    test_optimized_loader_earnings()
    
    print("\n" + "=" * 60)
    print("🎯 CURRENT YEAR EARNINGS TEST COMPLETE")
    print("=" * 60)
    print("If earnings are limited to current year, the fix is successful!")


if __name__ == "__main__":
    main()
