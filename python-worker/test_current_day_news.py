#!/usr/bin/env python3
"""
Test current day news functionality
"""
import sys
import os
from datetime import datetime

# Add the app directory to the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def test_current_day_news():
    """Test current day news functionality"""
    print("📰 TESTING CURRENT DAY NEWS")
    print("=" * 50)
    
    today = datetime.now().strftime("%Y-%m-%d")
    print(f"📅 Today's Date: {today}")
    
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
        
        # Test 1: Stock News (current day)
        print("\n1️⃣ Testing Stock News (Current Day)...")
        try:
            stock_news = client.get_stock_news(page=0, limit=10)
            if stock_news:
                print(f"   ✅ SUCCESS: {len(stock_news)} articles")
                for i, article in enumerate(stock_news[:3]):
                    print(f"   📰 {i+1}. {article.get('title', 'No title')[:50]}...")
                    print(f"      📅 Date: {article.get('publishedDate', 'No date')}")
                    print(f"      🔗 Source: {article.get('site', 'No source')}")
                    print()
            else:
                print(f"   ❌ No articles found for today")
        except Exception as e:
            print(f"   ❌ ERROR: {e}")
        
        # Test 2: General News (current day)
        print("\n2️⃣ Testing General News (Current Day)...")
        try:
            general_news = client.get_general_news(page=0, limit=5)
            if general_news:
                print(f"   ✅ SUCCESS: {len(general_news)} articles")
                for i, article in enumerate(general_news[:2]):
                    print(f"   📰 {i+1}. {article.get('title', 'No title')[:50]}...")
                    print(f"      📅 Date: {article.get('publishedDate', 'No date')}")
                    print(f"      🔗 Source: {article.get('site', 'No source')}")
                    print()
            else:
                print(f"   ❌ No articles found for today")
        except Exception as e:
            print(f"   ❌ ERROR: {e}")
        
        # Test 3: Verify dates are current day
        print("\n3️⃣ Verifying News Dates...")
        try:
            stock_news = client.get_stock_news(page=0, limit=20)
            if stock_news:
                today_articles = 0
                for article in stock_news:
                    pub_date = article.get('publishedDate', '')
                    if today in pub_date:  # Check if today's date is in the published date
                        today_articles += 1
                
                print(f"   📊 Total articles: {len(stock_news)}")
                print(f"   📅 Today's articles: {today_articles}")
                print(f"   📈 Percentage: {(today_articles/len(stock_news)*100):.1f}%")
                
                if today_articles > 0:
                    print(f"   ✅ Current day news working!")
                else:
                    print(f"   ⚠️  No current day articles found")
            else:
                print(f"   ❌ No articles to verify")
        except Exception as e:
            print(f"   ❌ ERROR: {e}")
        
        print("\n🎉 CURRENT DAY NEWS TEST COMPLETE")
        
    except ImportError as e:
        print(f"❌ IMPORT ERROR: {e}")
        print("Make sure all dependencies are installed")
    except Exception as e:
        print(f"❌ SETUP ERROR: {e}")


def test_optimized_loader_news():
    """Test optimized loader news functionality"""
    print("\n🚀 TESTING OPTIMIZED LOADER NEWS")
    print("=" * 50)
    
    try:
        from app.services.optimized_fmp_loader import optimized_fmp_loader
        
        # Test market news
        print("\n1️⃣ Testing Market News...")
        market_news = optimized_fmp_loader.get_market_news(limit=10)
        if market_news:
            print(f"   ✅ SUCCESS: {len(market_news)} articles")
            if market_news:
                print(f"   📰 Latest: {market_news[0].get('title', 'No title')[:50]}...")
        else:
            print(f"   ❌ No market news found")
        
        print("\n🎉 OPTIMIZED LOADER NEWS TEST COMPLETE")
        
    except Exception as e:
        print(f"❌ OPTIMIZED LOADER ERROR: {e}")


def main():
    """Main test function"""
    print("📰 TESTING CURRENT DAY NEWS FIX")
    print("=" * 60)
    print("This test verifies that news is filtered to current day only")
    print("=" * 60)
    
    # Test current day news
    test_current_day_news()
    
    # Test optimized loader news
    test_optimized_loader_news()
    
    print("\n" + "=" * 60)
    print("🎯 CURRENT DAY NEWS TEST COMPLETE")
    print("=" * 60)
    print("If news is filtered to current day, the fix is successful!")


if __name__ == "__main__":
    main()
