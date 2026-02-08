#!/usr/bin/env python3
"""
Quick test for new growth APIs
Tests the 4 new growth data types
"""

import requests
import json
from datetime import datetime

def test_growth_apis():
    """Test the new growth APIs"""
    base_url = "http://127.0.0.1:8001/api/v1/refresh"
    test_symbol = "AAPL"
    
    # New growth data types
    growth_data_types = [
        "income_statement_growth",
        "balance_sheet_growth", 
        "cash_flow_growth",
        "financial_growth"
    ]
    
    print("🚀 Testing New Growth APIs")
    print("="*50)
    
    for data_type in growth_data_types:
        print(f"\n📊 Testing {data_type} for {test_symbol}...")
        
        payload = {
            "symbols": [test_symbol],
            "data_types": [data_type],
            "force": True
        }
        
        try:
            response = requests.post(
                base_url,
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=30
            )
            
            if response.status_code == 200:
                result = response.json()
                symbol_result = result.get("results", {}).get(test_symbol, {})
                data_result = symbol_result.get("results", {}).get(data_type, {})
                
                status = data_result.get("status", "unknown")
                message = data_result.get("message", "No message")
                
                if status == "success":
                    print(f"✅ {data_type}: SUCCESS - {message}")
                elif status == "skipped":
                    print(f"⏭️ {data_type}: SKIPPED - {message}")
                else:
                    print(f"❌ {data_type}: FAILED - {message}")
                    
            else:
                print(f"❌ {data_type}: HTTP {response.status_code} - {response.text}")
                
        except Exception as e:
            print(f"❌ {data_type}: ERROR - {e}")
    
    print(f"\n🎯 Growth API Test completed at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

if __name__ == "__main__":
    test_growth_apis()
