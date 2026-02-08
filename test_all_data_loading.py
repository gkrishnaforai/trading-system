#!/usr/bin/env python3
"""
Comprehensive Test Script for All Data Loading
Tests all 25 data types from refresh strategy with rate limiting
"""

import time
import json
import requests
from datetime import datetime
from typing import Dict, List, Any

# Configuration
PYTHON_API_URL = "http://127.0.0.1:8001"
BASE_URL = "http://localhost:8502"

class DataLoadingTester:
    def __init__(self):
        self.python_api_url = PYTHON_API_URL
        self.results = {
            "success": True,
            "data": {},
            "symbols_loaded": 0,
            "data_types": [],
            "errors": [],
            "api_calls_made": [],
            "rate_limit_info": {
                "calls_per_minute_limit": 200,
                "total_calls_planned": 0,
                "estimated_time_minutes": 0
            },
            "test_summary": {
                "total_api_calls": 0,
                "successful_calls": 0,
                "failed_calls": 0,
                "skipped_calls": 0,
                "start_time": None,
                "end_time": None,
                "duration_seconds": 0
            }
        }
    
    def log_api_call(self, endpoint: str, symbol: str, data_type: str = None, call_number: int = 0):
        """Log API call for debugging"""
        if data_type:
            log_msg = f"POST {endpoint} for {symbol} - {data_type} (call #{call_number})"
        else:
            log_msg = f"POST {endpoint} for {symbol} (call #{call_number})"
        
        self.results["api_calls_made"].append(log_msg)
        print(f"📞 {log_msg}")
    
    def test_analyst_data_api(self, symbol: str, data_type: str) -> Dict[str, Any]:
        """Test analyst and grading data APIs"""
        try:
            if data_type == "stock_grades":
                endpoint = f"{self.python_api_url}/api/v1/grades/refresh/{symbol}"
            elif data_type == "consensus_data":
                endpoint = f"{self.python_api_url}/api/v1/grades/update-consensus/{symbol}"
            elif data_type in ["price_targets", "analyst_ratings"]:
                # These are part of stock grades
                endpoint = f"{self.python_api_url}/api/v1/grades/refresh/{symbol}"
            else:
                return {"status": "skipped", "message": f"Unknown analyst data type: {data_type}"}
            
            response = requests.post(endpoint, timeout=30)
            
            if response.status_code == 200:
                result = response.json()
                if result.get('success'):
                    results_count = result.get('results', {}).get('grades_loaded', 0)
                    return {
                        "status": "success",
                        "message": f"Loaded {results_count} items for {symbol}",
                        "response": result
                    }
                else:
                    return {
                        "status": "error",
                        "message": result.get('message', 'API returned failure'),
                        "response": result
                    }
            else:
                return {
                    "status": "error",
                    "message": f"HTTP {response.status_code}: {response.text}",
                    "http_status": response.status_code
                }
                
        except Exception as e:
            return {
                "status": "error",
                "message": f"Exception: {str(e)}"
            }
    
    def test_market_data_api(self, symbol: str, data_type: str) -> Dict[str, Any]:
        """Test market and financial data APIs"""
        try:
            endpoint = f"{self.python_api_url}/api/v1/refresh"
            payload = {
                "symbols": [symbol],
                "data_types": [data_type],
                "force": True,
            }
            
            response = requests.post(endpoint, json=payload, timeout=300)
            
            if response.status_code == 200:
                result = response.json()
                if result.get('success'):
                    return {
                        "status": "success",
                        "message": f"Refreshed {data_type} for {symbol}",
                        "response": result
                    }
                else:
                    return {
                        "status": "error",
                        "message": result.get('message', 'API returned failure'),
                        "response": result
                    }
            else:
                return {
                    "status": "error",
                    "message": f"HTTP {response.status_code}: {response.text}",
                    "http_status": response.status_code
                }
                
        except Exception as e:
            return {
                "status": "error",
                "message": f"Exception: {str(e)}"
            }
    
    def test_all_data_loading(self, data_types: List[str], symbols: List[str]) -> Dict[str, Any]:
        """Test all data loading with rate limiting"""
        print(f"🚀 Starting comprehensive data loading test...")
        print(f"📊 Data types: {len(data_types)}")
        print(f"📈 Symbols: {len(symbols)}")
        print(f"📞 Total API calls planned: {len(data_types) * len(symbols)}")
        
        # Update rate limiting info
        total_calls = len(symbols) * len(data_types)
        self.results["data_types"] = data_types
        self.results["rate_limit_info"]["total_calls_planned"] = total_calls
        self.results["rate_limit_info"]["estimated_time_minutes"] = max(1, (total_calls / 180))
        self.results["test_summary"]["start_time"] = datetime.now()
        
        # Rate limiting: 200 calls per minute = ~3.33 calls per second
        # We'll use 3 calls per second to be safe (1 call every 0.34 seconds)
        call_delay = 0.34  # seconds between calls
        calls_in_current_minute = 0
        minute_start_time = time.time()
        call_number = 0
        
        for symbol_idx, symbol in enumerate(symbols):
            print(f"\n📈 Processing symbol: {symbol} ({symbol_idx + 1}/{len(symbols)})")
            symbol_results = {}
            
            for data_type_idx, data_type in enumerate(data_types):
                try:
                    # Check rate limiting
                    current_time = time.time()
                    if current_time - minute_start_time >= 60:
                        # Reset minute counter
                        calls_in_current_minute = 0
                        minute_start_time = current_time
                        print(f"⏰ Minute reset - continuing with rate limiting")
                    
                    if calls_in_current_minute >= 180:  # Leave buffer for other calls
                        # Wait until next minute
                        wait_time = 60 - (current_time - minute_start_time)
                        if wait_time > 0:
                            print(f"⏱️ Rate limit reached - waiting {wait_time:.1f} seconds...")
                            time.sleep(wait_time)
                            calls_in_current_minute = 0
                            minute_start_time = time.time()
                    
                    # Small delay between calls to prevent bursting
                    if symbol_idx > 0 or data_type_idx > 0:
                        time.sleep(call_delay)
                    
                    calls_in_current_minute += 1
                    call_number += 1
                    
                    print(f"  🔄 Testing {data_type} for {symbol} ({data_type_idx + 1}/{len(data_types)})")
                    
                    # Test appropriate API
                    if data_type in ["stock_grades", "consensus_data", "price_targets", "analyst_ratings"]:
                        # Analyst & Grading Data
                        self.log_api_call(f"/api/v1/grades/refresh/{symbol}", symbol, data_type, call_number)
                        result = self.test_analyst_data_api(symbol, data_type)
                    elif data_type in [
                        "price_historical", "price_current", "price_intraday_5m",
                        "fundamentals", "income_statements", "balance_sheets", "cash_flow_statements",
                        "indicators", "financial_ratios", "key_metrics_ttm", "financial_scores",
                        "earnings", "earnings_transcripts", "news", "corporate_actions",
                        "industry_peers", "macro_market_data", "short_interest", "short_volume", 
                        "share_float", "risk_factors", "signals"
                    ]:
                        # Market & Financial Data
                        self.log_api_call("/api/v1/refresh", symbol, data_type, call_number)
                        result = self.test_market_data_api(symbol, data_type)
                    else:
                        # Not implemented
                        result = {
                            "status": "skipped",
                            "message": f"Data type '{data_type}' not yet implemented"
                        }
                    
                    # Add timestamp
                    result["timestamp"] = datetime.now().isoformat()
                    symbol_results[data_type] = result
                    
                    # Update counters
                    if result["status"] == "success":
                        self.results["test_summary"]["successful_calls"] += 1
                        print(f"    ✅ {result['message']}")
                    elif result["status"] == "error":
                        self.results["test_summary"]["failed_calls"] += 1
                        print(f"    ❌ {result['message']}")
                        self.results["errors"].append(f"Error with {data_type} for {symbol}: {result['message']}")
                    else:
                        self.results["test_summary"]["skipped_calls"] += 1
                        print(f"    ⏭️ {result['message']}")
                    
                    self.results["test_summary"]["total_api_calls"] += 1
                    
                except Exception as e:
                    error_result = {
                        "status": "error",
                        "message": f"Test exception: {str(e)}",
                        "timestamp": datetime.now().isoformat()
                    }
                    symbol_results[data_type] = error_result
                    self.results["test_summary"]["failed_calls"] += 1
                    self.results["errors"].append(f"Exception with {data_type} for {symbol}: {str(e)}")
                    print(f"    💥 Exception: {str(e)}")
            
            self.results["data"][symbol] = symbol_results
        
        self.results["symbols_loaded"] = len(symbols)
        self.results["test_summary"]["end_time"] = datetime.now()
        self.results["test_summary"]["duration_seconds"] = (
            self.results["test_summary"]["end_time"] - self.results["test_summary"]["start_time"]
        ).total_seconds()
        
        return self.results
    
    def print_summary(self):
        """Print test summary"""
        summary = self.results["test_summary"]
        
        print(f"\n" + "="*80)
        print(f"📊 COMPREHENSIVE DATA LOADING TEST SUMMARY")
        print(f"="*80)
        print(f"📅 Start Time: {summary['start_time']}")
        print(f"📅 End Time: {summary['end_time']}")
        print(f"⏱️ Duration: {summary['duration_seconds']:.1f} seconds")
        print(f"📞 Total API Calls: {summary['total_api_calls']}")
        print(f"✅ Successful: {summary['successful_calls']}")
        print(f"❌ Failed: {summary['failed_calls']}")
        print(f"⏭️ Skipped: {summary['skipped_calls']}")
        
        success_rate = (summary['successful_calls'] / summary['total_api_calls'] * 100) if summary['total_api_calls'] > 0 else 0
        print(f"📈 Success Rate: {success_rate:.1f}%")
        
        if self.results["errors"]:
            print(f"\n❌ ERRORS ({len(self.results['errors'])}):")
            for i, error in enumerate(self.results["errors"][:10]):  # Show first 10 errors
                print(f"  {i+1}. {error}")
            if len(self.results["errors"]) > 10:
                print(f"  ... and {len(self.results['errors']) - 10} more errors")
        
        print(f"\n🔧 Rate Limiting Info:")
        rate_info = self.results["rate_limit_info"]
        print(f"  📞 Calls per minute limit: {rate_info['calls_per_minute_limit']}")
        print(f"  📊 Total calls planned: {rate_info['total_calls_planned']}")
        print(f"  ⏱️ Estimated time: {rate_info['estimated_time_minutes']:.1f} minutes")
        print(f"  ⏱️ Actual time: {summary['duration_seconds']/60:.1f} minutes")
        
        print(f"\n" + "="*80)

def main():
    """Main test function"""
    print("🚀 Comprehensive Data Loading Test")
    print("="*80)
    
    # Initialize tester
    tester = DataLoadingTester()
    
    # All 29 data types from refresh strategy (updated with growth APIs)
    all_data_types = [
        # === MARKET DATA ===
        "price_historical", "price_current", "price_intraday_5m",
        # === FINANCIAL STATEMENTS ===
        "fundamentals", "income_statements", "balance_sheets", "cash_flow_statements",
        # === FINANCIAL METRICS ===
        "indicators", "financial_ratios", "key_metrics_ttm", "financial_scores",
        # === GROWTH METRICS (NEW) ===
        "income_statement_growth", "balance_sheet_growth", "cash_flow_growth", "financial_growth",
        # === ANALYST & GRADING DATA ===
        "stock_grades", "consensus_data", "price_targets", "analyst_ratings",
        # === EARNINGS DATA ===
        "earnings", "earnings_transcripts",
        # === NEWS & EVENTS ===
        "news", "corporate_actions",
        # === REFERENCE DATA ===
        "industry_peers", "macro_market_data",
        # === SPECIALIZED DATA ===
        "short_interest", "short_volume", "share_float", "risk_factors", "institutional_buying",
        # === SYSTEM DATA ===
        "signals"
    ]
    
    # Test symbols (smaller set for testing)
    test_symbols = ["AAPL", "MSFT", "GOOGL"]  # 3 symbols for testing (87 API calls)
    
    print(f"📊 Testing {len(all_data_types)} data types for {len(test_symbols)} symbols")
    print(f"📞 Total API calls: {len(all_data_types) * len(test_symbols)} (87 total)")
    print(f"⏱️ Estimated time: {(len(all_data_types) * len(test_symbols) / 180):.1f} minutes")
    
    # Run the test
    results = tester.test_all_data_loading(all_data_types, test_symbols)
    
    # Print summary
    tester.print_summary()
    
    # Save results to file
    output_file = f"data_loading_test_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(output_file, 'w') as f:
        # Convert datetime objects to strings for JSON serialization
        results_copy = results.copy()
        results_copy["test_summary"]["start_time"] = str(results_copy["test_summary"]["start_time"])
        results_copy["test_summary"]["end_time"] = str(results_copy["test_summary"]["end_time"])
        json.dump(results_copy, f, indent=2)
    
    print(f"\n💾 Detailed results saved to: {output_file}")
    
    return results

if __name__ == "__main__":
    main()
