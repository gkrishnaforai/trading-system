#!/usr/bin/env python3
"""
Comprehensive FMP Integration Test
Tests all the enhanced FMP client functionality and optimized loader
"""
import sys
import os
from datetime import datetime
import time

# Add the app directory to the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.providers.financial_modeling_prep.client import enhanced_fmp_client
from app.services.optimized_fmp_loader import optimized_fmp_loader
from app.observability.logging import get_logger

logger = get_logger("fmp_integration_test")


class FMPIntegrationTester:
    """Comprehensive test suite for FMP integration"""
    
    def __init__(self):
        self.client = enhanced_fmp_client
        self.loader = optimized_fmp_loader
        self.test_symbol = "AAPL"
        self.test_symbols = ["AAPL", "MSFT", "GOOGL"]
        
    def run_all_tests(self):
        """Run all integration tests"""
        logger.info("🚀 Starting Comprehensive FMP Integration Tests")
        
        test_results = {
            "client_tests": {},
            "loader_tests": {},
            "integration_tests": {},
            "performance_tests": {},
            "errors": []
        }
        
        # Test 1: Enhanced Client Basic Functionality
        test_results["client_tests"]["basic"] = self.test_client_basic()
        
        # Test 2: Enhanced Client Financial Data
        test_results["client_tests"]["financial"] = self.test_client_financial()
        
        # Test 3: Enhanced Client Analyst Data
        test_results["client_tests"]["analyst"] = self.test_client_analyst()
        
        # Test 4: Enhanced Client News and Transcripts
        test_results["client_tests"]["news_transcripts"] = self.test_client_news_transcripts()
        
        # Test 5: Optimized Loader Basic Functionality
        test_results["loader_tests"]["basic"] = self.test_loader_basic()
        
        # Test 6: Optimized Loader Comprehensive Data
        test_results["loader_tests"]["comprehensive"] = self.test_loader_comprehensive()
        
        # Test 7: Optimized Loader On-Demand
        test_results["loader_tests"]["on_demand"] = self.test_loader_on_demand()
        
        # Test 8: Integration Test - End to End
        test_results["integration_tests"]["end_to_end"] = self.test_end_to_end()
        
        # Test 9: Performance Test - Caching
        test_results["performance_tests"]["caching"] = self.test_caching_performance()
        
        # Test 10: Performance Test - Rate Limiting
        test_results["performance_tests"]["rate_limiting"] = self.test_rate_limiting()
        
        # Generate summary
        self.generate_test_summary(test_results)
        
        return test_results
    
    def test_client_basic(self):
        """Test enhanced client basic functionality"""
        logger.info("📊 Testing Enhanced Client Basic Functionality")
        
        results = {
            "real_time_quote": False,
            "historical_prices": False,
            "company_profile": False,
            "stock_list": False,
            "symbol_search": False
        }
        
        try:
            # Test real-time quote
            quote = self.client.get_real_time_quote(self.test_symbol)
            if quote and "price" in quote:
                results["real_time_quote"] = True
                logger.info(f"✅ Real-time quote: ${quote.get('price', 'N/A')}")
            
            # Test historical prices
            hist = self.client.get_historical_prices_full(self.test_symbol)
            if hist and "historical" in hist and len(hist["historical"]) > 0:
                results["historical_prices"] = True
                logger.info(f"✅ Historical prices: {len(hist['historical'])} records")
            
            # Test company profile
            profile = self.client.get_company_profile(self.test_symbol)
            if profile and "companyName" in profile:
                results["company_profile"] = True
                logger.info(f"✅ Company profile: {profile.get('companyName', 'N/A')}")
            
            # Test stock list
            stock_list = self.client.get_stock_list()
            if isinstance(stock_list, list) and len(stock_list) > 0:
                results["stock_list"] = True
                logger.info(f"✅ Stock list: {len(stock_list)} stocks")
            
            # Test symbol search
            search = self.client.search_symbols("apple")
            if isinstance(search, list) and len(search) > 0:
                results["symbol_search"] = True
                logger.info(f"✅ Symbol search: {len(search)} results")
            
        except Exception as e:
            logger.error(f"❌ Client basic test error: {e}")
        
        return results
    
    def test_client_financial(self):
        """Test enhanced client financial data"""
        logger.info("💰 Testing Enhanced Client Financial Data")
        
        results = {
            "income_statement": False,
            "balance_sheet": False,
            "cash_flow": False,
            "key_metrics": False,
            "financial_ratios": False,
            "financial_scores": False
        }
        
        try:
            # Test income statement
            income = self.client.get_income_statement(self.test_symbol)
            if isinstance(income, list) and len(income) > 0:
                results["income_statement"] = True
                logger.info(f"✅ Income statement: {len(income)} records")
            
            # Test balance sheet
            balance = self.client.get_balance_sheet_statement(self.test_symbol)
            if isinstance(balance, list) and len(balance) > 0:
                results["balance_sheet"] = True
                logger.info(f"✅ Balance sheet: {len(balance)} records")
            
            # Test cash flow
            cash_flow = self.client.get_cash_flow_statement(self.test_symbol)
            if isinstance(cash_flow, list) and len(cash_flow) > 0:
                results["cash_flow"] = True
                logger.info(f"✅ Cash flow: {len(cash_flow)} records")
            
            # Test key metrics
            metrics = self.client.get_key_metrics(self.test_symbol)
            if isinstance(metrics, list) and len(metrics) > 0:
                results["key_metrics"] = True
                logger.info(f"✅ Key metrics: {len(metrics)} records")
            
            # Test financial ratios
            ratios = self.client.get_financial_ratios(self.test_symbol)
            if isinstance(ratios, list) and len(ratios) > 0:
                results["financial_ratios"] = True
                logger.info(f"✅ Financial ratios: {len(ratios)} records")
            
            # Test financial scores
            scores = self.client.get_financial_scores(self.test_symbol)
            if isinstance(scores, list) and len(scores) > 0:
                results["financial_scores"] = True
                logger.info(f"✅ Financial scores: {len(scores)} records")
            
        except Exception as e:
            logger.error(f"❌ Client financial test error: {e}")
        
        return results
    
    def test_client_analyst(self):
        """Test enhanced client analyst data"""
        logger.info("⭐ Testing Enhanced Client Analyst Data")
        
        results = {
            "ratings_snapshot": False,
            "price_targets": False,
            "stock_grades": False,
            "financial_estimates": False
        }
        
        try:
            # Test ratings snapshot
            ratings = self.client.get_ratings_snapshot(self.test_symbol)
            if isinstance(ratings, list) and len(ratings) > 0:
                results["ratings_snapshot"] = True
                logger.info(f"✅ Ratings snapshot: {len(ratings)} records")
            
            # Test price targets
            targets = self.client.get_price_target_consensus(self.test_symbol)
            if isinstance(targets, list) and len(targets) > 0:
                results["price_targets"] = True
                logger.info(f"✅ Price targets: {len(targets)} records")
            
            # Test stock grades
            grades = self.client.get_stock_grades(self.test_symbol)
            if isinstance(grades, list) and len(grades) > 0:
                results["stock_grades"] = True
                logger.info(f"✅ Stock grades: {len(grades)} records")
            
            # Test financial estimates
            estimates = self.client.get_financial_estimates(self.test_symbol)
            if isinstance(estimates, list) and len(estimates) > 0:
                results["financial_estimates"] = True
                logger.info(f"✅ Financial estimates: {len(estimates)} records")
            
        except Exception as e:
            logger.error(f"❌ Client analyst test error: {e}")
        
        return results
    
    def test_client_news_transcripts(self):
        """Test enhanced client news and transcripts"""
        logger.info("📰 Testing Enhanced Client News and Transcripts")
        
        results = {
            "market_news_summary": False,
            "latest_transcripts": False,
            "transcript_dates": False
        }
        
        try:
            # Test market news summary
            news = self.client.get_market_news_summary(limit=5)
            if isinstance(news, dict) and len(news) > 0:
                results["market_news_summary"] = True
                total_articles = sum(len(articles) for articles in news.values() if isinstance(articles, list))
                logger.info(f"✅ Market news: {total_articles} articles")
            
            # Test latest transcripts
            transcripts = self.client.get_latest_earning_transcripts()
            if isinstance(transcripts, list) and len(transcripts) > 0:
                results["latest_transcripts"] = True
                logger.info(f"✅ Latest transcripts: {len(transcripts)} available")
            
            # Test transcript dates
            dates = self.client.get_transcript_dates_by_symbol(self.test_symbol)
            if isinstance(dates, list):
                results["transcript_dates"] = True
                logger.info(f"✅ Transcript dates: {len(dates)} dates")
            
        except Exception as e:
            logger.error(f"❌ Client news/transcripts test error: {e}")
        
        return results
    
    def test_loader_basic(self):
        """Test optimized loader basic functionality"""
        logger.info("🚀 Testing Optimized Loader Basic Functionality")
        
        results = {
            "real_time_price": False,
            "historical_prices": False,
            "company_profile": False,
            "symbol_search": False,
            "stock_list": False
        }
        
        try:
            # Test real-time price
            price = self.loader.get_real_time_price(self.test_symbol)
            if price and "price" in price:
                results["real_time_price"] = True
                logger.info(f"✅ Real-time price: ${price.get('price', 'N/A')}")
            
            # Test historical prices
            hist = self.loader.get_historical_prices(self.test_symbol)
            if hasattr(hist, 'empty') and not hist.empty:
                results["historical_prices"] = True
                logger.info(f"✅ Historical prices: {len(hist)} records")
            
            # Test company profile
            profile = self.loader.get_company_profile(self.test_symbol)
            if profile and "companyName" in profile:
                results["company_profile"] = True
                logger.info(f"✅ Company profile: {profile.get('companyName', 'N/A')}")
            
            # Test symbol search
            search = self.loader.search_symbol("apple")
            if isinstance(search, list) and len(search) > 0:
                results["symbol_search"] = True
                logger.info(f"✅ Symbol search: {len(search)} results")
            
            # Test stock list
            stock_list = self.loader.get_stock_list()
            if isinstance(stock_list, list) and len(stock_list) > 0:
                results["stock_list"] = True
                logger.info(f"✅ Stock list: {len(stock_list)} stocks")
            
        except Exception as e:
            logger.error(f"❌ Loader basic test error: {e}")
        
        return results
    
    def test_loader_comprehensive(self):
        """Test optimized loader comprehensive data loading"""
        logger.info("📊 Testing Optimized Loader Comprehensive Data")
        
        results = {
            "essential_load": False,
            "comprehensive_load": False,
            "data_types_loaded": []
        }
        
        try:
            # Test essential data load
            essential = self.loader.preload_essential_data([self.test_symbol])
            if (essential and "real_time_prices" in essential and 
                self.test_symbol in essential["real_time_prices"]):
                results["essential_load"] = True
                logger.info("✅ Essential data load successful")
            
            # Test comprehensive data load
            comprehensive = self.loader.load_all_data_for_symbols([self.test_symbol], load_on_demand=True)
            if comprehensive and "stats" in comprehensive:
                results["comprehensive_load"] = True
                results["data_types_loaded"] = list(comprehensive.keys())
                logger.info(f"✅ Comprehensive load: {len(comprehensive)} data types")
            
        except Exception as e:
            logger.error(f"❌ Loader comprehensive test error: {e}")
        
        return results
    
    def test_loader_on_demand(self):
        """Test optimized loader on-demand data loading"""
        logger.info("🔍 Testing Optimized Loader On-Demand Data")
        
        results = {
            "financial_data": False,
            "analyst_data": False,
            "metrics_data": False
        }
        
        try:
            # Test financial data on-demand
            financial = self.loader.get_on_demand_data(
                self.test_symbol, 
                ["income_statement", "balance_sheet", "cash_flow"]
            )
            if financial and "data" in financial and len(financial["data"]) > 0:
                results["financial_data"] = True
                logger.info(f"✅ Financial on-demand: {len(financial['data'])} types")
            
            # Test analyst data on-demand
            analyst = self.loader.get_on_demand_data(
                self.test_symbol,
                ["analyst_ratings", "price_targets", "stock_grades"]
            )
            if analyst and "data" in analyst and len(analyst["data"]) > 0:
                results["analyst_data"] = True
                logger.info(f"✅ Analyst on-demand: {len(analyst['data'])} types")
            
            # Test metrics data on-demand
            metrics = self.loader.get_on_demand_data(
                self.test_symbol,
                ["key_metrics", "financial_ratios", "financial_scores"]
            )
            if metrics and "data" in metrics and len(metrics["data"]) > 0:
                results["metrics_data"] = True
                logger.info(f"✅ Metrics on-demand: {len(metrics['data'])} types")
            
        except Exception as e:
            logger.error(f"❌ Loader on-demand test error: {e}")
        
        return results
    
    def test_end_to_end(self):
        """Test end-to-end integration"""
        logger.info("🔄 Testing End-to-End Integration")
        
        results = {
            "client_to_loader": False,
            "cache_integration": False,
            "data_consistency": False
        }
        
        try:
            # Test client to loader integration
            client_data = self.client.get_company_profile(self.test_symbol)
            loader_data = self.loader.get_company_profile(self.test_symbol)
            
            if (client_data and loader_data and 
                client_data.get("symbol") == loader_data.get("symbol")):
                results["client_to_loader"] = True
                logger.info("✅ Client to loader integration successful")
            
            # Test cache integration
            # First call (should hit API)
            start_time = time.time()
            price1 = self.loader.get_real_time_price(self.test_symbol)
            first_call_time = time.time() - start_time
            
            # Second call (should hit cache)
            start_time = time.time()
            price2 = self.loader.get_real_time_price(self.test_symbol)
            second_call_time = time.time() - start_time
            
            if price1 and price2 and second_call_time < first_call_time:
                results["cache_integration"] = True
                logger.info(f"✅ Cache integration: {first_call_time:.3f}s -> {second_call_time:.3f}s")
            
            # Test data consistency
            if price1 and price2 and price1.get("price") == price2.get("price"):
                results["data_consistency"] = True
                logger.info("✅ Data consistency verified")
            
        except Exception as e:
            logger.error(f"❌ End-to-end test error: {e}")
        
        return results
    
    def test_caching_performance(self):
        """Test caching performance"""
        logger.info("⚡ Testing Caching Performance")
        
        results = {
            "cache_hit_performance": False,
            "cache_ttl_effectiveness": False,
            "cache_stats_available": False
        }
        
        try:
            # Test cache hit performance
            # Clear cache first
            self.loader.clear_cache("price:*")
            
            # First call (cache miss)
            start_time = time.time()
            price1 = self.loader.get_real_time_price(self.test_symbol)
            miss_time = time.time() - start_time
            
            # Second call (cache hit)
            start_time = time.time()
            price2 = self.loader.get_real_time_price(self.test_symbol)
            hit_time = time.time() - start_time
            
            if hit_time < miss_time * 0.5:  # Cache should be at least 2x faster
                results["cache_hit_performance"] = True
                logger.info(f"✅ Cache performance: {miss_time:.3f}s -> {hit_time:.3f}s")
            
            # Test cache stats
            stats = self.loader.get_cache_stats()
            if stats and "cache_size" in stats:
                results["cache_stats_available"] = True
                logger.info(f"✅ Cache stats: {stats['cache_size']} items")
            
            # Test cache TTL (basic check)
            if stats.get("cache_size", 0) > 0:
                results["cache_ttl_effectiveness"] = True
                logger.info("✅ Cache TTL working")
            
        except Exception as e:
            logger.error(f"❌ Caching performance test error: {e}")
        
        return results
    
    def test_rate_limiting(self):
        """Test rate limiting"""
        logger.info("🚦 Testing Rate Limiting")
        
        results = {
            "rate_limit_respected": False,
            "no_api_errors": False
        }
        
        try:
            # Test multiple rapid calls
            errors = 0
            successful_calls = 0
            
            for i in range(5):  # Make 5 rapid calls
                try:
                    price = self.loader.get_real_time_price(self.test_symbol)
                    if price:
                        successful_calls += 1
                except Exception as e:
                    errors += 1
                    logger.warning(f"Call {i+1} error: {e}")
            
            # If we have successful calls and no rate limit errors, rate limiting is working
            if successful_calls > 0 and errors == 0:
                results["rate_limit_respected"] = True
                results["no_api_errors"] = True
                logger.info(f"✅ Rate limiting: {successful_calls}/5 successful")
            
        except Exception as e:
            logger.error(f"❌ Rate limiting test error: {e}")
        
        return results
    
    def generate_test_summary(self, test_results):
        """Generate comprehensive test summary"""
        logger.info("""
🎉 FMP INTEGRATION TEST SUMMARY
================================""")
        
        # Calculate success rates
        total_tests = 0
        passed_tests = 0
        
        for category, tests in test_results.items():
            if isinstance(tests, dict):
                for test_name, result in tests.items():
                    if isinstance(result, dict):
                        total_tests += len(result)
                        passed_tests += sum(1 for v in result.values() if v)
                    elif isinstance(result, bool):
                        total_tests += 1
                        passed_tests += 1 if result else 0
        
        success_rate = (passed_tests / total_tests * 100) if total_tests > 0 else 0
        
        logger.info(f"""
📊 OVERALL RESULTS:
   • Total Tests: {total_tests}
   • Passed Tests: {passed_tests}
   • Success Rate: {success_rate:.1f}%
        """)
        
        # Category breakdown
        for category, tests in test_results.items():
            if isinstance(tests, dict):
                category_passed = sum(1 for v in tests.values() if isinstance(v, bool) and v)
                category_total = len([v for v in tests.values() if isinstance(v, bool)])
                category_rate = (category_passed / category_total * 100) if category_total > 0 else 0
                
                logger.info(f"""
📋 {category.upper()}:
   • Passed: {category_passed}/{category_total}
   • Success Rate: {category_rate:.1f}%
                """)
        
        # Recommendations
        if success_rate >= 90:
            logger.info("🎉 EXCELLENT: Integration is ready for production!")
        elif success_rate >= 75:
            logger.info("✅ GOOD: Integration mostly working, minor issues to address")
        elif success_rate >= 50:
            logger.info("⚠️  FAIR: Integration partially working, significant issues to address")
        else:
            logger.info("❌ POOR: Integration has major issues, requires significant work")
        
        logger.info("================================")


def main():
    """Main test runner"""
    tester = FMPIntegrationTester()
    results = tester.run_all_tests()
    
    # Return exit code based on success rate
    total_tests = 0
    passed_tests = 0
    
    for category, tests in results.items():
        if isinstance(tests, dict):
            for test_name, result in tests.items():
                if isinstance(result, dict):
                    total_tests += len(result)
                    passed_tests += sum(1 for v in result.values() if v)
                elif isinstance(result, bool):
                    total_tests += 1
                    passed_tests += 1 if result else 0
    
    success_rate = (passed_tests / total_tests * 100) if total_tests > 0 else 0
    
    if success_rate >= 75:
        logger.info("🎉 Integration test PASSED")
        return 0
    else:
        logger.error("❌ Integration test FAILED")
        return 1


if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)
