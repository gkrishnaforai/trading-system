#!/usr/bin/env python3
"""
Comprehensive Test Suite for Admin Dashboard Functionality
Tests all SQL queries, API endpoints, and dashboard features
"""

import pytest
import requests
import json
from typing import Dict, List, Any
import sys
import os

# Add the app directory to Python path
sys.path.append(os.path.join(os.path.dirname(__file__), 'app'))

from app.database import db
from app.config import settings

class AdminDashboardTestSuite:
    """Test suite for admin dashboard functionality"""
    
    def __init__(self, base_url: str = "http://127.0.0.1:8001"):
        self.base_url = base_url
        self.session = requests.Session()
        self.session.timeout = 30
        
    def log_test(self, test_name: str, status: str, details: str = ""):
        """Log test results"""
        status_icon = "✅" if status == "PASS" else "❌" if status == "FAIL" else "⚠️"
        print(f"{status_icon} {test_name}: {status}")
        if details:
            print(f"   Details: {details}")
    
    def test_api_health(self) -> bool:
        """Test if API server is running"""
        try:
            response = self.session.get(f"{self.base_url}/health")
            if response.status_code == 200:
                self.log_test("API Health Check", "PASS", f"Status: {response.json().get('status')}")
                return True
            else:
                self.log_test("API Health Check", "FAIL", f"Status Code: {response.status_code}")
                return False
        except Exception as e:
            self.log_test("API Health Check", "FAIL", str(e))
            return False
    
    def test_table_exists(self, table_name: str) -> bool:
        """Test if a table exists in the database"""
        try:
            query = """
                SELECT EXISTS (
                    SELECT FROM information_schema.tables 
                    WHERE table_name = :table_name
                );
            """
            result = db.execute_query(query, {"table_name": table_name})
            exists = result[0]['exists'] if result else False
            
            if exists:
                self.log_test(f"Table {table_name}", "PASS", "Table exists")
                return True
            else:
                self.log_test(f"Table {table_name}", "FAIL", "Table does not exist")
                return False
        except Exception as e:
            self.log_test(f"Table {table_name}", "FAIL", str(e))
            return False
    
    def test_table_columns(self, table_name: str) -> Dict[str, bool]:
        """Test if table has expected columns"""
        try:
            query = """
                SELECT column_name, data_type 
                FROM information_schema.columns 
                WHERE table_name = :table_name
                ORDER BY ordinal_position;
            """
            result = db.execute_query(query, {"table_name": table_name})
            
            columns = {row['column_name']: True for row in result} if result else {}
            
            # Check for common columns
            has_symbol = 'symbol' in columns
            has_date = 'date' in columns
            has_created_at = 'created_at' in columns
            
            self.log_test(f"Columns {table_name}", "PASS", 
                         f"symbol: {has_symbol}, date: {has_date}, created_at: {has_created_at}")
            
            return {
                'has_symbol': has_symbol,
                'has_date': has_date,
                'has_created_at': has_created_at,
                'all_columns': columns
            }
        except Exception as e:
            self.log_test(f"Columns {table_name}", "FAIL", str(e))
            return {
                'has_symbol': False,
                'has_date': False,
                'has_created_at': False,
                'all_columns': {}
            }
    
    def test_safe_quality_query(self, table_name: str, columns_info: Dict[str, bool]) -> bool:
        """Test a safe quality query based on available columns"""
        try:
            if columns_info['has_symbol'] and columns_info['has_date']:
                # Standard case: has both symbol and date
                query = f"""
                    SELECT 
                        COUNT(*) as total,
                        COUNT(*) FILTER (WHERE symbol IS NOT NULL AND date IS NOT NULL) as non_null_rows,
                        CASE 
                            WHEN COUNT(*) > 0 THEN COUNT(*) FILTER (WHERE symbol IS NOT NULL AND date IS NOT NULL) * 100.0 / COUNT(*)
                            ELSE 0.0 
                        END as null_rate,
                        CASE 
                            WHEN COUNT(*) > 0 THEN COUNT(DISTINCT symbol || date) * 100.0 / COUNT(*)
                            ELSE 0.0 
                        END as duplicate_rate
                    FROM {table_name}
                """
            elif columns_info['has_symbol']:
                # Has symbol but no date
                query = f"""
                    SELECT 
                        COUNT(*) as total,
                        COUNT(*) FILTER (WHERE symbol IS NOT NULL) as non_null_rows,
                        CASE 
                            WHEN COUNT(*) > 0 THEN COUNT(*) FILTER (WHERE symbol IS NOT NULL) * 100.0 / COUNT(*)
                            ELSE 0.0 
                        END as null_rate,
                        0.0 as duplicate_rate
                    FROM {table_name}
                """
            elif columns_info['has_created_at']:
                # Has created_at but no symbol
                query = f"""
                    SELECT 
                        COUNT(*) as total,
                        COUNT(*) as total_rows,
                        100.0 as null_rate,
                        0.0 as duplicate_rate
                    FROM {table_name}
                """
            else:
                # No standard columns, just count
                query = f"SELECT COUNT(*) as total, COUNT(*) as total_rows, 100.0 as null_rate, 0.0 as duplicate_rate FROM {table_name}"
            
            result = db.execute_query(query)
            if result:
                row = result[0]
                self.log_test(f"Quality Query {table_name}", "PASS", 
                             f"Total: {row.get('total', 0)}, Null Rate: {row.get('null_rate', 0)}%")
                return True
            else:
                self.log_test(f"Quality Query {table_name}", "FAIL", "No results")
                return False
                
        except Exception as e:
            self.log_test(f"Quality Query {table_name}", "FAIL", str(e))
            return False
    
    def test_admin_data_summary_endpoint(self, table_name: str) -> bool:
        """Test admin data summary endpoint"""
        try:
            response = self.session.get(f"{self.base_url}/admin/data-summary/{table_name}")
            
            if response.status_code == 200:
                data = response.json()
                if data.get('success'):
                    self.log_test(f"Endpoint {table_name}", "PASS", 
                                 f"Records: {data.get('data', {}).get('total_records', 0)}")
                    return True
                else:
                    self.log_test(f"Endpoint {table_name}", "FAIL", data.get('error', 'Unknown error'))
                    return False
            elif response.status_code == 400:
                error_data = response.json()
                self.log_test(f"Endpoint {table_name}", "FAIL", error_data.get('detail', 'Bad request'))
                return False
            else:
                self.log_test(f"Endpoint {table_name}", "FAIL", f"Status Code: {response.status_code}")
                return False
                
        except Exception as e:
            self.log_test(f"Endpoint {table_name}", "FAIL", str(e))
            return False
    
    def test_stocks_api_endpoints(self) -> bool:
        """Test all stocks API endpoints"""
        stocks_endpoints = [
            ("GET", "/api/v1/stocks/available"),
            ("GET", "/api/v1/stocks/search/AAPL"),
            ("GET", "/api/v1/stocks/AAPL"),
            ("GET", "/api/v1/stocks/AAPL/coverage"),
        ]
        
        all_passed = True
        
        for method, endpoint in stocks_endpoints:
            try:
                if method == "GET":
                    response = self.session.get(f"{self.base_url}{endpoint}")
                
                if response.status_code == 200:
                    data = response.json()
                    if data.get('success'):
                        self.log_test(f"Stocks API {endpoint}", "PASS", "Success response")
                    else:
                        self.log_test(f"Stocks API {endpoint}", "FAIL", data.get('error', 'API error'))
                        all_passed = False
                else:
                    self.log_test(f"Stocks API {endpoint}", "FAIL", f"Status: {response.status_code}")
                    all_passed = False
                    
            except Exception as e:
                self.log_test(f"Stocks API {endpoint}", "FAIL", str(e))
                all_passed = False
        
        return all_passed
    
    def test_audit_endpoints(self) -> bool:
        """Test audit endpoints"""
        audit_endpoints = [
            "/api/v1/audit/provider-distribution/2024-01-01",
            "/api/v1/audit/fmp-status/2024-01-01",
            "/api/v1/audit/symbol-availability/2024-01-01",
        ]
        
        all_passed = True
        
        for endpoint in audit_endpoints:
            try:
                response = self.session.get(f"{self.base_url}{endpoint}")
                
                if response.status_code == 200:
                    data = response.json()
                    if data.get('success'):
                        self.log_test(f"Audit API {endpoint}", "PASS", "Success response")
                    else:
                        self.log_test(f"Audit API {endpoint}", "FAIL", data.get('error', 'API error'))
                        all_passed = False
                else:
                    self.log_test(f"Audit API {endpoint}", "FAIL", f"Status: {response.status_code}")
                    all_passed = False
                    
            except Exception as e:
                self.log_test(f"Audit API {endpoint}", "FAIL", str(e))
                all_passed = False
        
        return all_passed
    
    def run_comprehensive_test(self) -> Dict[str, Any]:
        """Run comprehensive test suite"""
        print("🚀 Starting Comprehensive Admin Dashboard Test Suite")
        print("=" * 60)
        
        results = {
            'total_tests': 0,
            'passed_tests': 0,
            'failed_tests': 0,
            'tables_tested': [],
            'issues_found': []
        }
        
        # Test API health
        results['total_tests'] += 1
        if self.test_api_health():
            results['passed_tests'] += 1
        else:
            results['failed_tests'] += 1
            results['issues_found'].append("API server not running")
            return results  # Stop if API is down
        
        # Test valid tables
        valid_tables = [
            "raw_market_data_daily", "raw_market_data_intraday", "indicators_daily",
            "fundamentals_snapshots", "industry_peers", "market_news", "earnings_data",
            "macro_market_data", "stocks", "data_ingestion_runs", "data_ingestion_events",
            "stock_grades", "stock_consensus_history", "analyst_firm_rankings", 
            "grade_changes", "grade_change_events", "rating_change_log",
            "financial_ratios", "financial_statements", "income_statements", 
            "balance_sheets", "cash_flow_statements", "corporate_actions",
            "fmp_company_profiles", "fmp_market_news", "fmp_real_time_prices",
            "key_metrics_ttm", "financial_scores", "earnings_transcripts", 
            "short_interest", "short_volume", "share_float", "risk_factors"
        ]
        
        print("\n📊 Testing Database Tables")
        print("-" * 30)
        
        for table in valid_tables:
            print(f"\nTesting table: {table}")
            
            # Test table exists
            results['total_tests'] += 1
            table_exists = self.test_table_exists(table)
            if table_exists:
                results['passed_tests'] += 1
                results['tables_tested'].append(table)
                
                # Test table columns
                results['total_tests'] += 1
                columns_info = self.test_table_columns(table)
                if columns_info:
                    results['passed_tests'] += 1
                    
                    # Test safe quality query
                    results['total_tests'] += 1
                    if self.test_safe_quality_query(table, columns_info):
                        results['passed_tests'] += 1
                    else:
                        results['failed_tests'] += 1
                        results['issues_found'].append(f"Quality query failed for {table}")
                else:
                    results['failed_tests'] += 1
                    results['issues_found'].append(f"Column check failed for {table}")
                
                # Test admin endpoint
                results['total_tests'] += 1
                if self.test_admin_data_summary_endpoint(table):
                    results['passed_tests'] += 1
                else:
                    results['failed_tests'] += 1
                    results['issues_found'].append(f"Admin endpoint failed for {table}")
            else:
                results['failed_tests'] += 1
                results['issues_found'].append(f"Table {table} does not exist")
        
        print("\n🔧 Testing API Endpoints")
        print("-" * 30)
        
        # Test stocks API
        results['total_tests'] += 1
        if self.test_stocks_api_endpoints():
            results['passed_tests'] += 1
        else:
            results['failed_tests'] += 1
            results['issues_found'].append("Stocks API endpoints failed")
        
        # Test audit endpoints
        results['total_tests'] += 1
        if self.test_audit_endpoints():
            results['passed_tests'] += 1
        else:
            results['failed_tests'] += 1
            results['issues_found'].append("Audit endpoints failed")
        
        # Print summary
        print("\n" + "=" * 60)
        print("📊 TEST SUMMARY")
        print("=" * 60)
        print(f"Total Tests: {results['total_tests']}")
        print(f"✅ Passed: {results['passed_tests']}")
        print(f"❌ Failed: {results['failed_tests']}")
        print(f"📈 Success Rate: {(results['passed_tests'] / results['total_tests'] * 100):.1f}%")
        
        if results['issues_found']:
            print("\n🔍 Issues Found:")
            for i, issue in enumerate(results['issues_found'], 1):
                print(f"{i}. {issue}")
        
        return results

def main():
    """Main test runner"""
    # Check if API server is running
    import subprocess
    import time
    
    print("🔍 Checking if Python Worker API is running...")
    
    # Try to start the API server if not running
    try:
        response = requests.get("http://127.0.0.1:8001/health", timeout=5)
        print("✅ API server is running")
    except:
        print("❌ API server is not running")
        print("Please start the API server first:")
        print("cd /Users/krishnag/tools/trading-system/python-worker")
        print("python start_api_server.py")
        return
    
    # Run tests
    test_suite = AdminDashboardTestSuite()
    results = test_suite.run_comprehensive_test()
    
    # Exit with appropriate code
    sys.exit(0 if results['failed_tests'] == 0 else 1)

if __name__ == "__main__":
    main()
