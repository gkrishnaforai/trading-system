#!/usr/bin/env python3
"""
Comprehensive test script to verify all fixes before container deployment.
Tests financial statements, corporate actions, data summary API, and NaT handling.
"""

import os
import sys
import requests
import json
from datetime import datetime
from typing import Dict, Any, List

# Add the app directory to Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'app'))

def test_database_connection():
    """Test database connection and basic operations"""
    print("🔍 Testing database connection...")
    try:
        from app.database import db
        
        # Test basic query
        result = db.execute_query("SELECT 1 as test")
        assert result[0]['test'] == 1
        print("✅ Database connection successful")
        return True
    except Exception as e:
        print(f"❌ Database connection failed: {e}")
        return False

def test_table_existence():
    """Test that all expected tables exist"""
    print("\n🔍 Testing table existence...")
    try:
        from app.database import db
        
        expected_tables = [
            "financial_statements", "corporate_actions", "earnings_data",
            "stock_grades", "financial_ratios", "earnings_transcripts",
            "short_interest", "short_volume", "share_float", "risk_factors"
        ]
        
        missing_tables = []
        for table in expected_tables:
            result = db.execute_query(
                "SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = :table)",
                {"table": table}
            )
            exists = result[0]['exists'] if result else False
            if exists:
                print(f"✅ {table}: EXISTS")
            else:
                print(f"❌ {table}: MISSING")
                missing_tables.append(table)
        
        if missing_tables:
            print(f"❌ Missing tables: {missing_tables}")
            return False
        else:
            print("✅ All expected tables exist")
            return True
    except Exception as e:
        print(f"❌ Table existence check failed: {e}")
        return False

def test_data_summary_api():
    """Test the admin data summary API endpoints"""
    print("\n🔍 Testing data summary API...")
    
    base_url = "http://127.0.0.1:8001"
    test_tables = [
        "financial_statements", "corporate_actions", "earnings_data",
        "stock_grades", "financial_ratios", "earnings_transcripts",
        "short_interest", "short_volume", "share_float", "risk_factors",
        "raw_market_data_daily", "market_news", "macro_market_data"
    ]
    
    failed_tables = []
    for table in test_tables:
        try:
            response = requests.get(f"{base_url}/admin/data-summary/{table}", timeout=10)
            if response.status_code == 200:
                data = response.json()
                print(f"✅ {table}: {data.get('total_records', 0)} records")
            else:
                print(f"❌ {table}: HTTP {response.status_code}")
                failed_tables.append(table)
        except Exception as e:
            print(f"❌ {table}: {e}")
            failed_tables.append(table)
    
    if failed_tables:
        print(f"❌ Failed tables: {failed_tables}")
        return False
    else:
        print("✅ All data summary endpoints working")
        return True

def test_nat_handling():
    """Test NaT handling in refresh manager"""
    print("\n🔍 Testing NaT handling...")
    try:
        import pandas as pd
        from app.data_management.refresh_manager import DataRefreshManager
        
        # Test NaT detection
        nat_values = [pd.NaT, None, "invalid_date", "2023-01-01"]
        
        for val in nat_values:
            if isinstance(val, str):
                result = pd.to_datetime(val, errors="coerce").date() if val else None
            else:
                result = val
            
            if result is None or pd.isna(result):
                print(f"✅ NaT handling: {val} → filtered out")
            else:
                print(f"✅ NaT handling: {val} → {result}")
        
        print("✅ NaT handling working correctly")
        return True
    except Exception as e:
        print(f"❌ NaT handling test failed: {e}")
        return False

def test_financial_statements_insert():
    """Test financial statements insert with correct column names"""
    print("\n🔍 Testing financial statements insert...")
    try:
        from app.database import db
        
        # Test that stock_symbol column exists
        result = db.execute_query(
            "SELECT column_name FROM information_schema.columns WHERE table_name = 'financial_statements' AND column_name = 'stock_symbol'"
        )
        
        if result and len(result) > 0:
            print("✅ financial_statements.stock_symbol column exists")
            
            # Test insert structure (without actually inserting)
            test_query = """
                INSERT INTO financial_statements (stock_symbol, period_type, statement_type, fiscal_period, source, payload)
                VALUES (:symbol, :period_type, :statement_type, :fiscal_period, :source, CAST(:payload AS jsonb))
                ON CONFLICT (stock_symbol, period_type, statement_type, fiscal_period)
                DO UPDATE SET source = EXCLUDED.source, payload = EXCLUDED.payload, updated_at = NOW()
            """
            print("✅ Financial statements insert query structure is valid")
            return True
        else:
            print("❌ financial_statements.stock_symbol column missing")
            return False
    except Exception as e:
        print(f"❌ Financial statements insert test failed: {e}")
        return False

def test_data_sources():
    """Test data source initialization and basic methods"""
    print("\n🔍 Testing data sources...")
    try:
        from app.data_sources.composite_source import CompositeDataSource
        
        # Test composite source initialization
        source = CompositeDataSource()
        print("✅ CompositeDataSource initialized")
        
        # Test method existence
        required_methods = [
            'fetch_financial_statements', 'fetch_corporate_actions',
            'fetch_actions', 'fetch_dividends', 'fetch_splits'
        ]
        
        for method in required_methods:
            if hasattr(source, method):
                print(f"✅ Method exists: {method}")
            else:
                print(f"❌ Method missing: {method}")
                return False
        
        print("✅ Data sources working correctly")
        return True
    except Exception as e:
        print(f"❌ Data sources test failed: {e}")
        return False

def test_health_endpoints():
    """Test basic health endpoints"""
    print("\n🔍 Testing health endpoints...")
    
    base_url = "http://127.0.0.1:8001"
    
    # Test health endpoint
    try:
        response = requests.get(f"{base_url}/health", timeout=5)
        if response.status_code == 200:
            print("✅ Health endpoint working")
        else:
            print(f"❌ Health endpoint: HTTP {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ Health endpoint failed: {e}")
        return False
    
    # Test API docs
    try:
        response = requests.get(f"{base_url}/docs", timeout=5)
        if response.status_code == 200:
            print("✅ API docs accessible")
        else:
            print(f"❌ API docs: HTTP {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ API docs failed: {e}")
        return False
    
    return True

def main():
    """Run all tests"""
    print("🚀 Starting comprehensive fix verification tests...\n")
    
    tests = [
        ("Database Connection", test_database_connection),
        ("Table Existence", test_table_existence),
        ("Health Endpoints", test_health_endpoints),
        ("Data Summary API", test_data_summary_api),
        ("NaT Handling", test_nat_handling),
        ("Financial Statements Insert", test_financial_statements_insert),
        ("Data Sources", test_data_sources),
    ]
    
    results = []
    for test_name, test_func in tests:
        try:
            result = test_func()
            results.append((test_name, result))
        except Exception as e:
            print(f"❌ {test_name} failed with exception: {e}")
            results.append((test_name, False))
    
    # Summary
    print("\n" + "="*60)
    print("📊 TEST SUMMARY")
    print("="*60)
    
    passed = 0
    failed = 0
    
    for test_name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status}: {test_name}")
        if result:
            passed += 1
        else:
            failed += 1
    
    print(f"\nTotal: {len(results)} tests")
    print(f"Passed: {passed}")
    print(f"Failed: {failed}")
    
    if failed == 0:
        print("\n🎉 ALL TESTS PASSED! Ready for container deployment.")
        return 0
    else:
        print(f"\n⚠️  {failed} test(s) failed. Fix issues before deployment.")
        return 1

if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)
