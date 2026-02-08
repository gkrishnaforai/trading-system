#!/usr/bin/env python3
"""
Comprehensive Test for Admin Dashboard Fixes
Tests all problematic tables and API endpoints
"""

import sys
import os
import requests
from typing import Dict, List, Any

# Add the app directory to Python path
sys.path.append(os.path.join(os.path.dirname(__file__), 'app'))

from app.database import db

class DashboardFixesTest:
    """Test all dashboard fixes"""
    
    def __init__(self, base_url: str = "http://127.0.0.1:8001"):
        self.base_url = base_url
        self.session = requests.Session()
        self.session.timeout = 30
        self.results = []
        
    def log_test(self, test_name: str, status: str, details: str = ""):
        """Log test results"""
        status_icon = "✅" if status == "PASS" else "❌" if status == "FAIL" else "⚠️"
        print(f"{status_icon} {test_name}: {status}")
        if details:
            print(f"   Details: {details}")
        self.results.append({
            'test': test_name,
            'status': status,
            'details': details
        })
    
    def test_api_health(self) -> bool:
        """Test API health"""
        try:
            response = self.session.get(f"{self.base_url}/health", timeout=5)
            if response.status_code == 200:
                self.log_test("API Health", "PASS", "API server is running")
                return True
            else:
                self.log_test("API Health", "FAIL", f"Status: {response.status_code}")
                return False
        except Exception as e:
            self.log_test("API Health", "FAIL", str(e))
            return False
    
    def test_problematic_tables(self) -> Dict[str, bool]:
        """Test all problematic tables"""
        problematic_tables = [
            "data_ingestion_events",
            "share_float", 
            "risk_factors",
            "stocks"
        ]
        
        results = {}
        
        print("\n🔍 Testing Problematic Tables")
        print("=" * 40)
        
        for table in problematic_tables:
            print(f"\nTesting: {table}")
            
            # Test admin endpoint
            try:
                response = self.session.get(f"{self.base_url}/admin/data-summary/{table}")
                
                if response.status_code == 200:
                    data = response.json()
                    if data.get('success'):
                        records = data.get('data', {}).get('total_records', 0)
                        self.log_test(f"Endpoint {table}", "PASS", f"Records: {records}")
                        results[table] = True
                    else:
                        self.log_test(f"Endpoint {table}", "FAIL", data.get('error', 'API error'))
                        results[table] = False
                else:
                    self.log_test(f"Endpoint {table}", "FAIL", f"Status: {response.status_code}")
                    results[table] = False
                    
            except Exception as e:
                self.log_test(f"Endpoint {table}", "FAIL", str(e))
                results[table] = False
        
        return results
    
    def test_stocks_api(self) -> bool:
        """Test stocks API endpoints"""
        stocks_endpoints = [
            ("GET", "/api/v1/stocks/available"),
            ("GET", "/api/v1/stocks/search/AAPL"),
            ("GET", "/api/v1/stocks/AAPL/coverage"),
        ]
        
        all_passed = True
        
        print("\n🔧 Testing Stocks API")
        print("=" * 30)
        
        for method, endpoint in stocks_endpoints:
            try:
                if method == "GET":
                    response = self.session.get(f"{self.base_url}{endpoint}")
                
                if response.status_code == 200:
                    data = response.json()
                    if data.get('success'):
                        self.log_test(f"Stocks {endpoint}", "PASS", "Success response")
                    else:
                        self.log_test(f"Stocks {endpoint}", "FAIL", data.get('error', 'API error'))
                        all_passed = False
                else:
                    self.log_test(f"Stocks {endpoint}", "FAIL", f"Status: {response.status_code}")
                    all_passed = False
                    
            except Exception as e:
                self.log_test(f"Stocks {endpoint}", "FAIL", str(e))
                all_passed = False
        
        return all_passed
    
    def test_removed_tables(self) -> bool:
        """Test that removed tables return proper errors"""
        removed_tables = ["weekly_aggregation", "growth_calculations"]
        
        print("\n🗑️ Testing Removed Tables")
        print("=" * 35)
        
        all_correct = True
        
        for table in removed_tables:
            try:
                response = self.session.get(f"{self.base_url}/admin/data-summary/{table}")
                
                if response.status_code == 400:
                    self.log_test(f"Removed {table}", "PASS", "Correctly returns 400 error")
                else:
                    self.log_test(f"Removed {table}", "FAIL", f"Should return 400, got {response.status_code}")
                    all_correct = False
                    
            except Exception as e:
                self.log_test(f"Removed {table}", "FAIL", str(e))
                all_correct = False
        
        return all_correct
    
    def test_sample_valid_tables(self) -> bool:
        """Test a sample of valid tables"""
        sample_tables = [
            "raw_market_data_daily",
            "indicators_daily", 
            "market_news",
            "fundamentals_snapshots"
        ]
        
        print("\n📊 Testing Sample Valid Tables")
        print("=" * 40)
        
        all_passed = True
        
        for table in sample_tables:
            try:
                response = self.session.get(f"{self.base_url}/admin/data-summary/{table}")
                
                if response.status_code == 200:
                    data = response.json()
                    if data.get('success'):
                        records = data.get('data', {}).get('total_records', 0)
                        self.log_test(f"Valid {table}", "PASS", f"Records: {records}")
                    else:
                        self.log_test(f"Valid {table}", "FAIL", data.get('error', 'API error'))
                        all_passed = False
                else:
                    self.log_test(f"Valid {table}", "FAIL", f"Status: {response.status_code}")
                    all_passed = False
                    
            except Exception as e:
                self.log_test(f"Valid {table}", "FAIL", str(e))
                all_passed = False
        
        return all_passed
    
    def run_comprehensive_test(self) -> Dict[str, Any]:
        """Run comprehensive test suite"""
        print("🚀 Comprehensive Dashboard Fixes Test")
        print("=" * 50)
        
        # Test API health
        if not self.test_api_health():
            print("❌ API server is not running. Please start it first:")
            print("   cd /Users/krishnag/tools/trading-system/python-worker")
            print("   python start_api_server.py")
            return {'status': 'FAILED', 'reason': 'API server not running'}
        
        # Run all tests
        problematic_results = self.test_problematic_tables()
        stocks_api_result = self.test_stocks_api()
        removed_tables_result = self.test_removed_tables()
        valid_tables_result = self.test_sample_valid_tables()
        
        # Calculate results
        total_tests = len(self.results)
        passed_tests = len([r for r in self.results if r['status'] == 'PASS'])
        failed_tests = len([r for r in self.results if r['status'] == 'FAIL'])
        
        # Summary
        print("\n" + "=" * 50)
        print("📊 TEST SUMMARY")
        print("=" * 50)
        print(f"Total Tests: {total_tests}")
        print(f"✅ Passed: {passed_tests}")
        print(f"❌ Failed: {failed_tests}")
        print(f"📈 Success Rate: {(passed_tests / total_tests * 100):.1f}%")
        
        # Detailed results
        print(f"\n🔍 Problematic Tables: {sum(problematic_results.values())}/{len(problematic_results)} passed")
        print(f"🔧 Stocks API: {'✅ PASSED' if stocks_api_result else '❌ FAILED'}")
        print(f"🗑️ Removed Tables: {'✅ PASSED' if removed_tables_result else '❌ FAILED'}")
        print(f"📊 Valid Tables: {'✅ PASSED' if valid_tables_result else '❌ FAILED'}")
        
        # Failed tests details
        failed_tests_list = [r for r in self.results if r['status'] == 'FAIL']
        if failed_tests_list:
            print(f"\n❌ Failed Tests:")
            for i, test in enumerate(failed_tests_list, 1):
                print(f"   {i}. {test['test']}: {test['details']}")
        
        return {
            'total_tests': total_tests,
            'passed_tests': passed_tests,
            'failed_tests': failed_tests,
            'success_rate': passed_tests / total_tests * 100,
            'problematic_results': problematic_results,
            'stocks_api_result': stocks_api_result,
            'removed_tables_result': removed_tables_result,
            'valid_tables_result': valid_tables_result,
            'all_passed': failed_tests == 0
        }

def main():
    """Main test runner"""
    tester = DashboardFixesTest()
    results = tester.run_comprehensive_test()
    
    if results['all_passed']:
        print("\n🎉 ALL TESTS PASSED! Dashboard fixes are working correctly.")
        print("\n✅ Ready to use:")
        print("   - Admin Dashboard at http://localhost:8501/Comprehensive_Admin_Dashboard")
        print("   - All problematic tables fixed")
        print("   - Stocks API working correctly")
        print("   - Non-existent tables properly handled")
    else:
        print(f"\n⚠️  {results['failed_tests']} test(s) failed. Please check the details above.")
    
    return results

if __name__ == "__main__":
    main()
